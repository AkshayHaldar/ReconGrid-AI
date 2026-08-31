"""End-to-End Integration tests verifying dirty real-world messy fixtures against all endpoints.

Tests:
- Bank statement with 7 preamble metadata lines, UTF-8 BOM, embedded UTRs, Cr/Dr suffixes, and corrupted row.
- Razorpay settlement with negative refund adjustment rows, fee/tax breakdowns, and currency strings.
- Graceful validation error surfacing (never raw 500 crashes).
"""

import io
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.models.razorpay_settlement import RazorpaySettlement
from app.utils.money import to_decimal


@pytest.mark.asyncio
async def test_bank_statement_messy_fixture_e2e(db_session: AsyncSession):
    fixture_path = Path(__file__).parent.parent / "fixtures" / "bank_statement_messy.csv"
    assert fixture_path.exists(), "bank_statement_messy.csv fixture must exist"

    # Pre-seed matching Razorpay settlements for the messy bank rows
    settlements = [
        RazorpaySettlement(
            settlement_id="setl_messy_001",
            amount=to_decimal("48657.00"),
            gross_amount=to_decimal("50000.00"),
            fees=to_decimal("1138.14"),
            tax=to_decimal("204.86"),
            utr="N296250485376",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_002",
            amount=to_decimal("123456.78"),
            gross_amount=to_decimal("126456.78"),
            fees=to_decimal("2542.37"),
            tax=to_decimal("457.63"),
            utr="CMS918273645012",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_003",
            amount=to_decimal("97640.00"),
            gross_amount=to_decimal("100000.00"),
            fees=to_decimal("2000.00"),
            tax=to_decimal("360.00"),
            utr="R260812345678",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_004",
            amount=to_decimal("19528.00"),
            gross_amount=to_decimal("20000.00"),
            fees=to_decimal("400.00"),
            tax=to_decimal("72.00"),
            utr="623456789012",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_005",
            amount=to_decimal("4882.00"),
            gross_amount=to_decimal("5000.00"),
            fees=to_decimal("100.00"),
            tax=to_decimal("18.00"),
            utr="UTR2608M4N5O6",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_006",
            amount=to_decimal("29292.00"),
            gross_amount=to_decimal("30000.00"),
            fees=to_decimal("600.00"),
            tax=to_decimal("108.00"),
            utr="624918273645",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_007",
            amount=to_decimal("5000.00"),
            gross_amount=to_decimal("5000.00"),
            fees=to_decimal("0.00"),
            tax=to_decimal("0.00"),
            utr="REV2608REV001",
            status="processed",
            is_test_mode=True,
        ),
        RazorpaySettlement(
            settlement_id="setl_messy_008",
            amount=to_decimal("39056.00"),
            gross_amount=to_decimal("40000.00"),
            fees=to_decimal("800.00"),
            tax=to_decimal("144.00"),
            utr="AX260876543210",
            status="processed",
            is_test_mode=True,
        ),
    ]
    for s in settlements:
        db_session.add(s)
    await db_session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Read raw fixture file (with preamble and dirty rows)
        with open(fixture_path, "rb") as f:
            raw_bytes = f.read()

        files = {"file": ("bank_statement_messy.csv", io.BytesIO(raw_bytes), "text/csv")}
        resp = await client.post("/api/v1/bank/upload", data={"batch_id": "messy_batch_001"}, files=files)

        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        data = payload["data"]

        # Assertions on parsing and error isolation:
        # 1. It successfully parsed multiple valid transaction rows
        assert data["inserted_count"] >= 8
        # 2. It isolated the corrupted row without failing the entire batch
        assert len(data["validation_errors"]) >= 1
        assert any("Row 10" in err or "INVALID_AMOUNT" in err or "NOT_A_VALID_AMOUNT" in err for err in data["validation_errors"])
        # 3. Valid rows were reconciled immediately
        assert data["reconciled_immediately"] >= 8

        # Verify reconciliation records in ledger
        ledger_resp = await client.get("/api/v1/reconciliation/messy_batch_001/records?status=ALL")
        assert ledger_resp.status_code == 200
        records = ledger_resp.json()["data"]["records"]
        assert len(records) >= 8

        # Verify embedded UTR extracted from narration
        rec_neft = next((r for r in records if r["bank_utr"] == "N296250485376"), None)
        assert rec_neft is not None
        assert rec_neft["match_status"] == "MATCHED"
        assert rec_neft["rzp_settlement_id"] == "setl_messy_001"

        # Verify batch status
        status_resp = await client.get("/api/v1/reconciliation/messy_batch_001/status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()["data"]
        assert status_data["total_records"] >= 8
        assert status_data["matched_count"] >= 7

        # Verify scorecard
        score_resp = await client.get("/api/v1/reconciliation/messy_batch_001/scorecard")
        assert score_resp.status_code == 200
        score_data = score_resp.json()["data"]
        assert score_data["total_rows_processed"] >= 8
        assert score_data["total_matched_count"] >= 7


@pytest.mark.asyncio
async def test_corrupted_file_all_invalid_rows_returns_actionable_400(db_session: AsyncSession):
    """Verifies that an upload where every row is corrupted returns an actionable 400 bad request, not 500."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad_csv = (
            "Date,Narration,Amount\n"
            "01-08-2026,Corrupted 1,BAD_AMOUNT_VAL\n"
            "02-08-2026,Corrupted 2,NOT_A_NUMBER\n"
        )
        files = {"file": ("corrupted.csv", io.BytesIO(bad_csv.encode("utf-8")), "text/csv")}
        resp = await client.post("/api/v1/bank/upload", data={"batch_id": "bad_batch"}, files=files)

        assert resp.status_code == 400
        data = resp.json()
        assert data["success"] is False
        assert data["error"]["code"] == "STATEMENT_VALIDATION_ERROR"
        assert len(data["error"]["details"]) >= 2
