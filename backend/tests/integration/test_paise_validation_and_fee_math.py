"""Integration tests for unscaled paise ingestion validation and demo seed fee-math alignment."""

import io
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.diagnostics import DiagnosticsService
from app.services.ingestion import IngestionService
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, to_decimal


@pytest.mark.asyncio
async def test_paise_row_ingestion_validation_and_batch_resilience(db_session: AsyncSession):
    """Asserts that unscaled paise rows are rejected with explicit validation errors

    while legitimate rows process normally without failing the whole batch.
    """
    service = IngestionService(db_session)

    # CSV with 1 legitimate row (₹5,000.00), 1 unscaled paise row (500000), and 1 legitimate large row (₹5,00,000.00)
    csv_content = (
        "Date,Chq/Ref No.,Narration,Deposit Amt.,Withdrawal Amt.\n"
        "24/08/2026,CMS002938491801,CMS/002938491801/HDFC/LEGIT_1,5000.00,0.00\n"
        "24/08/2026,CMS002938491802,CMS/002938491802/HDFC/PAISE_ROW,500000,0.00\n"
        "24/08/2026,CMS002938491803,CMS/002938491803/HDFC/LARGE_LEGIT,500000.00,0.00\n"
    ).encode("utf-8")

    file = UploadFile_wrapper = pytest.importorskip("fastapi").UploadFile(
        filename="mixed_statement.csv",
        file=io.BytesIO(csv_content),
        headers={"content-type": "text/csv"},
    )

    resp = await service.ingest_csv(file, batch_id="paise_test_batch")

    # 1. Total rows parsed in CSV stream: 3 (2 valid + 1 rejected)
    assert resp.total_rows_parsed == 3

    # 2. Legitimate rows inserted: 2 (5000.00 and 500000.00)
    assert resp.inserted_count == 2
    assert resp.duplicate_count == 0

    # 3. Paise row rejected with specific error message
    assert len(resp.validation_errors) == 1
    err_msg = resp.validation_errors[0]
    assert "Row 2" in err_msg
    assert "500000 appears to be unscaled paise" in err_msg
    assert "expected rupees with 2 decimal places" in err_msg


@pytest.mark.asyncio
async def test_demo_seed_fee_math_alignment_produces_zero_fee_mismatch_exceptions(db_session: AsyncSession):
    """Asserts that standard fee math in demo seed aligns with DiagnosticsService,

    producing zero unexplained exceptions from fee calculation drift.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Seed 60 demo records
        seed_resp = await client.post("/api/v1/demo/seed?count=60&batch_id=fee_alignment_batch")
        assert seed_resp.status_code == 200
        seed_data = seed_resp.json()
        assert seed_data["success"] is True

        summary = seed_data["data"]["summary"]
        assert summary["total_records"] >= 60
        assert summary["match_rate_percentage"] >= 85.0

        # Fetch records and check Tier 3 fee diagnostic records
        records_resp = await client.get("/api/v1/reconciliation/fee_alignment_batch/records?status=ALL&page_size=100")
        assert records_resp.status_code == 200
        records = records_resp.json()["data"]["records"]

        # Check Order #4521 (fee deduction)
        fee_records = [r for r in records if "4521" in r["bank_description"]]
        assert len(fee_records) >= 1
        for rec in fee_records:
            assert rec["match_status"] == "MATCHED"
            assert rec["diagnostic_type"] == "FEE_DEDUCTION"
            assert "matches Gateway Fee" in rec["diagnostic_note"]
            assert "1,180.00" in rec["diagnostic_note"]


def test_calculate_standard_fees_shared_function():
    """Unit test for shared calculate_standard_fees function."""
    fees, tax, net = calculate_standard_fees(Decimal("100000.00"))
    assert fees == Decimal("2000.00")
    assert tax == Decimal("360.00")
    assert net == Decimal("97640.00")
    assert (fees + tax + net) == Decimal("100000.00")

    fees2, tax2, net2 = calculate_standard_fees(Decimal("50000.00"))
    assert fees2 == Decimal("1000.00")
    assert tax2 == Decimal("180.00")
    assert net2 == Decimal("48820.00")
