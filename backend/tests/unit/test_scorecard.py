"""Unit and Integration tests for Reconciliation Scorecard API and conservation proof."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.schemas.reconciliation import ScorecardExceptionItem, ScorecardResponse
from app.services.reconciliation import ReconciliationEngine


@pytest.mark.asyncio
async def test_scorecard_api_endpoint_and_record_conservation(db_session: AsyncSession):
    """Asserts GET /reconciliation/{batch_id}/scorecard returns separate per-tier counts,

    measured throughput, zero-float Decimal types, and satisfies mathematical conservation.
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    batch_id = "test_scorecard_api_batch"

    # Setup distinct settlements
    # 1. Exact match target
    s1 = RazorpaySettlement(
        settlement_id="setl_sc_001",
        amount=Decimal("10000.00"),
        gross_amount=Decimal("10000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="CMSSC001",
        status="processed",
        settlement_created_at=now - timedelta(days=1),
        raw_payload={},
        is_test_mode=True,
    )
    # 2. Date fallback target
    s2 = RazorpaySettlement(
        settlement_id="setl_sc_002",
        amount=Decimal("20000.00"),
        gross_amount=Decimal("20000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="SETLNOUTR_SC",
        status="processed",
        settlement_created_at=now - timedelta(days=1),
        raw_payload={},
        is_test_mode=True,
    )
    db_session.add_all([s1, s2])
    await db_session.flush()

    # Setup bank transactions
    # 1. Tier 1 match (10,000)
    tx1 = BankTransaction(
        date=now - timedelta(days=1),
        amount=Decimal("10000.00"),
        direction="CREDIT",
        utr="CMSSC001",
        description="CMS/CMSSC001/HDFC/PAYOUT",
        row_hash="hash_sc_1",
        batch_id=batch_id,
    )
    # 2. Tier 0 fallback (20,000, no bank UTR)
    tx2 = BankTransaction(
        date=now - timedelta(days=1),
        amount=Decimal("20000.00"),
        direction="CREDIT",
        utr=None,
        description="DIRECT CR CLEARING",
        row_hash="hash_sc_2",
        batch_id=batch_id,
    )
    # 3. Genuine exception (> 5 days old, no settlement)
    tx3 = BankTransaction(
        date=now - timedelta(days=8),
        amount=Decimal("7500.00"),
        direction="CREDIT",
        utr="ICIC00992812",
        description="UNKNOWN MERCHANT DIRECT TRANSFER",
        row_hash="hash_sc_3",
        batch_id=batch_id,
    )
    # 4. Pending data (2 days old, no settlement)
    tx4 = BankTransaction(
        date=now - timedelta(days=2),
        amount=Decimal("3500.00"),
        direction="CREDIT",
        utr="CMSPENDING99",
        description="CMS/CMSPENDING99/HDFC/RECENT",
        row_hash="hash_sc_4",
        batch_id=batch_id,
    )
    db_session.add_all([tx1, tx2, tx3, tx4])
    await db_session.flush()

    # Run reconciliation
    await engine.reconcile_batch([tx1, tx2, tx3, tx4], [s1, s2], batch_id=batch_id)
    await db_session.commit()

    # Test GET scorecard endpoint
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(f"/api/v1/reconciliation/{batch_id}/scorecard")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]

        # 1. Volume & Timing
        assert data["total_rows_processed"] == 4
        assert Decimal(str(data["processing_time_seconds"])) > Decimal("0.0000")
        assert Decimal(str(data["rows_per_second"])) > Decimal("0.00")

        # 2. Per-tier counts (separate, not merged)
        assert data["tier_1_count"] == 1
        assert data["tier_0_count"] == 1

        # 3. Status breakdown
        assert data["total_matched_count"] == 1
        assert data["total_suggested_count"] == 1
        assert data["total_exception_count"] == 1
        assert data["total_pending_count"] == 1
        assert data["total_conflict_count"] == 0

        # 4. Conservation proof
        assert data["records_accounted_for"] == 4
        assert data["unaccounted_records"] == 0
        assert data["is_fully_accounted"] is True

        # 5. Complete exception list verification
        assert len(data["exceptions"]) == 1
        exc = data["exceptions"][0]
        assert exc["bank_transaction_id"] == tx3.id
        assert Decimal(str(exc["amount"])) == Decimal("7500.00")
        assert exc["reason_code"] == "UNRESOLVED"
        assert "UNKNOWN MERCHANT DIRECT TRANSFER" in exc["description"]


def test_scorecard_schema_rejects_floats():
    """Validates that ScorecardResponse strictly enforces zero float usage."""
    valid_data = {
        "batch_id": "b1",
        "total_rows_processed": 10,
        "processing_time_seconds": Decimal("0.0125"),
        "rows_per_second": Decimal("800.00"),
        "tier_0_count": 1,
        "tier_0_percentage": Decimal("10.00"),
        "tier_1_count": 7,
        "tier_1_percentage": Decimal("70.00"),
        "tier_2_count": 0,
        "tier_2_percentage": Decimal("0.00"),
        "tier_3_count": 0,
        "tier_3_percentage": Decimal("0.00"),
        "total_matched_count": 7,
        "total_matched_percentage": Decimal("70.00"),
        "total_suggested_count": 1,
        "total_suggested_percentage": Decimal("10.00"),
        "total_conflict_count": 0,
        "total_conflict_percentage": Decimal("0.00"),
        "total_exception_count": 2,
        "total_exception_percentage": Decimal("20.00"),
        "total_pending_count": 0,
        "total_pending_percentage": Decimal("0.00"),
        "total_reconciled_amount": Decimal("70000.00"),
        "total_ingested_amount": Decimal("100000.00"),
        "total_exception_amount": Decimal("20000.00"),
        "total_pending_amount": Decimal("0.00"),
        "records_accounted_for": 10,
        "unaccounted_records": 0,
        "is_fully_accounted": True,
        "exceptions": [],
    }

    # Should succeed with Decimal
    sc = ScorecardResponse(**valid_data)
    assert sc.total_rows_processed == 10

    # Should reject float in monetary field
    invalid_monetary = valid_data.copy()
    invalid_monetary["total_reconciled_amount"] = 70000.50
    with pytest.raises(ValidationError):
        ScorecardResponse(**invalid_monetary)

    # Should reject float in percentage field
    invalid_pct = valid_data.copy()
    invalid_pct["total_matched_percentage"] = 70.0
    with pytest.raises(ValidationError):
        ScorecardResponse(**invalid_pct)
