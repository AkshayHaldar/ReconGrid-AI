"""Unit & Integration tests for PENDING_SETTLEMENT_DATA intermediate status,

age-based eligibility window, and retry-on-sync transitions.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, to_decimal


@pytest.mark.asyncio
async def test_pending_settlement_within_window_becomes_pending(db_session: AsyncSession):
    """(Requirement 5a) A bank row within the 5-day recency window with no settlement

    must be classified as PENDING_SETTLEMENT_DATA (not EXCEPTION).
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # Bank row 2 days ago (within 5-day window)
    tx = BankTransaction(
        date=now - timedelta(days=2),
        amount=Decimal("15000.00"),
        direction="CREDIT",
        utr="CMSPENDING001",
        description="CMS/CMSPENDING001/HDFC/RECENT TX",
        row_hash="hash_pending_001",
        batch_id="pending_test_batch",
    )
    db_session.add(tx)
    await db_session.flush()

    # Reconcile with empty settlements
    logs = await engine.reconcile_batch([tx], [], batch_id="pending_test_batch")

    assert len(logs) == 1
    log = logs[0]
    assert log.match_status == "PENDING_SETTLEMENT_DATA"
    assert log.diagnostic_type == "PENDING_SETTLEMENT"
    assert "Awaiting settlement data from Razorpay" in log.diagnostic_note
    assert "5-day settlement window" in log.diagnostic_note
    assert log.delta_amount == Decimal("15000.00")
    assert log.superseded is False

    # Check metrics
    summary = await recon_repo.get_summary_metrics("pending_test_batch")
    assert summary["pending_count"] == 1
    assert summary["exception_count"] == 0
    assert summary["total_pending_amount"] == Decimal("15000.00")
    assert summary["total_exception_amount"] == Decimal("0.00")


@pytest.mark.asyncio
async def test_pending_row_transitions_to_matched_on_later_sync(db_session: AsyncSession):
    """(Requirement 5b) A row in PENDING_SETTLEMENT_DATA state transitions to MATCHED

    when a subsequent sync brings the missing settlement, writing an append-only log.
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # 1. Initial pass: Bank row arrives without matching settlement
    tx = BankTransaction(
        date=now - timedelta(days=1),
        amount=Decimal("25000.00"),
        direction="CREDIT",
        utr="CMSPENDING002",
        description="CMS/CMSPENDING002/HDFC/PAYOUT",
        row_hash="hash_pending_002",
        batch_id="sync_retry_batch",
    )
    db_session.add(tx)
    await db_session.flush()

    initial_logs = await engine.reconcile_batch([tx], [], batch_id="sync_retry_batch")
    assert len(initial_logs) == 1
    first_log = initial_logs[0]
    assert first_log.match_status == "PENDING_SETTLEMENT_DATA"
    assert first_log.superseded is False

    # 2. Simulated subsequent sync: Razorpay settlement arrives with matching UTR
    fees, tax, net = calculate_standard_fees(Decimal("25000.00"))
    setl = RazorpaySettlement(
        settlement_id="setl_sync_new_002",
        amount=Decimal("25000.00"),
        gross_amount=Decimal("25000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="CMSPENDING002",
        status="processed",
        settlement_created_at=now - timedelta(hours=12),
        raw_payload={},
        is_test_mode=True,
    )
    db_session.add(setl)
    await db_session.flush()

    # Re-run reconciliation on the batch (simulating sync trigger)
    second_logs = await engine.reconcile_batch([tx], [setl], batch_id="sync_retry_batch")
    assert len(second_logs) == 1
    second_log = second_logs[0]

    # Verify transition to MATCHED
    assert second_log.match_status == "MATCHED"
    assert second_log.match_tier == "TIER_1"
    assert "Auto-resolved from PENDING_SETTLEMENT_DATA on settlement sync" in second_log.diagnostic_note
    assert second_log.superseded is False

    # Verify append-only immutability: first log is still in DB, marked superseded
    refreshed_first = await recon_repo.get_by_id(first_log.id)
    assert refreshed_first is not None
    assert refreshed_first.match_status == "PENDING_SETTLEMENT_DATA"
    assert refreshed_first.superseded is True


@pytest.mark.asyncio
async def test_pending_row_transitions_to_exception_after_window_expires(db_session: AsyncSession):
    """(Requirement 5c) A row previously in PENDING_SETTLEMENT_DATA that has aged past

    the recency window without a settlement transitions to EXCEPTION on next sync pass.
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # 1. Row was initially 3 days old (within 5-day window)
    tx = BankTransaction(
        date=now - timedelta(days=3),
        amount=Decimal("12000.00"),
        direction="CREDIT",
        utr="CMSPENDING003",
        description="CMS/CMSPENDING003/HDFC/EXPIRING",
        row_hash="hash_pending_003",
        batch_id="expiry_batch",
    )
    db_session.add(tx)
    await db_session.flush()

    logs1 = await engine.reconcile_batch([tx], [], batch_id="expiry_batch")
    assert logs1[0].match_status == "PENDING_SETTLEMENT_DATA"

    # 2. Simulate passage of time: bank transaction date is now 7 days old (> 5-day window)
    tx.date = now - timedelta(days=7)
    await db_session.flush()

    # Next sync pass with still no matching settlement
    logs2 = await engine.reconcile_batch([tx], [], batch_id="expiry_batch")
    assert len(logs2) == 1
    expired_log = logs2[0]

    assert expired_log.match_status == "EXCEPTION"
    assert expired_log.diagnostic_type == "UNRESOLVED"
    assert "No matching Razorpay settlement found after pending window expired" in expired_log.diagnostic_note
    assert expired_log.superseded is False

    # Check metrics
    summary = await recon_repo.get_summary_metrics("expiry_batch")
    assert summary["pending_count"] == 0
    assert summary["exception_count"] == 1
    assert summary["total_exception_amount"] == Decimal("12000.00")


@pytest.mark.asyncio
async def test_older_row_goes_straight_to_exception(db_session: AsyncSession):
    """(Requirement 5d) A bank row older than the recency window from the start

    (e.g. 8 days ago) goes straight to EXCEPTION without ever being PENDING_SETTLEMENT_DATA.
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # Bank row 8 days ago (> 5 days)
    tx = BankTransaction(
        date=now - timedelta(days=8),
        amount=Decimal("40000.00"),
        direction="CREDIT",
        utr="CMSOLD004",
        description="CMS/CMSOLD004/HDFC/OLD RECORD",
        row_hash="hash_old_004",
        batch_id="old_batch",
    )
    db_session.add(tx)
    await db_session.flush()

    logs = await engine.reconcile_batch([tx], [], batch_id="old_batch")
    assert len(logs) == 1
    log = logs[0]

    assert log.match_status == "EXCEPTION"
    assert log.diagnostic_type == "UNRESOLVED"
    assert "No matching Razorpay settlement found for bank row" in log.diagnostic_note
    assert "pending window" not in log.diagnostic_note


@pytest.mark.asyncio
async def test_api_filter_by_pending_settlement_data(db_session: AsyncSession):
    """(Requirement 4) GET /reconciliation/{batch_id}/records?status=PENDING_SETTLEMENT_DATA

    filters and returns pending records.
    """
    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    tx1 = BankTransaction(
        date=now - timedelta(days=1),
        amount=Decimal("10000.00"),
        direction="CREDIT",
        utr="CMSAPI001",
        description="CMS/CMSAPI001/HDFC/PENDING",
        row_hash="hash_api_001",
        batch_id="api_pending_batch",
    )
    tx2 = BankTransaction(
        date=now - timedelta(days=9),
        amount=Decimal("20000.00"),
        direction="CREDIT",
        utr="CMSAPI002",
        description="CMS/CMSAPI002/HDFC/EXCEPTION",
        row_hash="hash_api_002",
        batch_id="api_pending_batch",
    )
    db_session.add_all([tx1, tx2])
    await db_session.flush()

    await engine.reconcile_batch([tx1, tx2], [], batch_id="api_pending_batch")
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Filter by PENDING_SETTLEMENT_DATA
        resp = await client.get("/api/v1/reconciliation/api_pending_batch/records?status=PENDING_SETTLEMENT_DATA")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_count"] == 1
        assert data["records"][0]["match_status"] == "PENDING_SETTLEMENT_DATA"
        assert data["records"][0]["bank_amount"] == 10000.0 or str(data["records"][0]["bank_amount"]) == "10000.00"

        # 2. Filter by EXCEPTION
        exc_resp = await client.get("/api/v1/reconciliation/api_pending_batch/records?status=EXCEPTION")
        assert exc_resp.status_code == 200
        exc_data = exc_resp.json()["data"]
        assert exc_data["total_count"] == 1
        assert exc_data["records"][0]["match_status"] == "EXCEPTION"

        # 3. Check status summary endpoint
        status_resp = await client.get("/api/v1/reconciliation/api_pending_batch/status")
        assert status_resp.status_code == 200
        s_data = status_resp.json()["data"]
        assert s_data["pending_count"] == 1
        assert s_data["exception_count"] == 1
        assert s_data["total_records"] == 2
