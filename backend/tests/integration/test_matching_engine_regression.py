"""Matching Engine Regression Tests across All Root-Cause Categories.

Verifies through HTTP API endpoints and direct service calls that:
1. Refund adjustments & clawbacks match deterministically with fee diagnostics.
2. Date window tolerance (T+1 to T+3 / up to 72h) matches non-UTR deposits.
3. Gross vs net comparisons resolve without false exceptions.
4. Reference / UTR normalization matches across banking prefix variations.
5. Batched payouts (pairs and triplets) match single bank lump-sum deposits.
6. Genuine external deposits remain strictly classified as UNRESOLVED EXCEPTION.
7. Precision is preserved and true exceptions are never artificially converted to false matches.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, to_decimal


@pytest.mark.asyncio
async def test_matching_engine_all_six_categories_regression(db_session: AsyncSession):
    """End-to-end regression test validating all 6 root cause categories."""
    batch_id = "test_matching_regression_batch"
    now = datetime.now(timezone.utc)

    # 1. Category (a): Refund adjustment (Net 45k, gross 50k, fee 1000, tax 180, refund 3820)
    gross_a = Decimal("50000.00")
    fees_a, tax_a, net_a = calculate_standard_fees(gross_a)
    refund_a = Decimal("3820.00")
    s_a = RazorpaySettlement(
        settlement_id="setl_reg_a",
        amount=net_a,
        gross_amount=gross_a,
        fees=fees_a,
        tax=tax_a,
        utr="REF296250485376",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={"refund_total": str(refund_a)},
        is_test_mode=True,
    )
    tx_a = BankTransaction(
        date=now - timedelta(days=6),
        amount=net_a - refund_a,  # 48820 - 3820 = 45000.00
        direction="CREDIT",
        utr="REF296250485376",
        description="NEFT/REF296250485376/RAZORPAY REFUND ADJ",
        row_hash="hash_reg_a",
        batch_id=batch_id,
    )

    # 2. Category (b): Date window (T+2.5 days = 60 hours, amount 82,000.00, no UTR)
    s_b = RazorpaySettlement(
        settlement_id="setl_reg_b",
        amount=Decimal("82000.00"),
        gross_amount=Decimal("82000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="SETL_INTERNAL_002",
        status="processed",
        settlement_created_at=now - timedelta(days=8, hours=12),
        raw_payload={},
        is_test_mode=True,
    )
    tx_b = BankTransaction(
        date=now - timedelta(days=6),
        amount=Decimal("82000.00"),
        direction="CREDIT",
        utr=None,
        description="DIRECT INWARD CLEARING NO UTR",
        row_hash="hash_reg_b",
        batch_id=batch_id,
    )

    # 3. Category (c): Gross vs Net (Settlement gross 100k, Bank received net 97,640)
    gross_c = Decimal("100000.00")
    fees_c, tax_c, net_c = calculate_standard_fees(gross_c)
    s_c = RazorpaySettlement(
        settlement_id="setl_reg_c",
        amount=gross_c,
        gross_amount=gross_c,
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="CMS998877665544",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={},
        is_test_mode=True,
    )
    tx_c = BankTransaction(
        date=now - timedelta(days=6),
        amount=net_c,
        direction="CREDIT",
        utr="CMS998877665544",
        description="CMS/CMS998877665544/RAZORPAY NET PAYOUT",
        row_hash="hash_reg_c",
        batch_id=batch_id,
    )

    # 4. Category (d): UTR Normalization (Settlement has 260812345678, Bank has NEFT-HDFC-260812345678)
    s_d = RazorpaySettlement(
        settlement_id="setl_reg_d",
        amount=Decimal("25000.00"),
        gross_amount=Decimal("25000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="260812345678",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={},
        is_test_mode=True,
    )
    tx_d = BankTransaction(
        date=now - timedelta(days=6),
        amount=Decimal("25000.00"),
        direction="CREDIT",
        utr="NEFT-HDFC-260812345678",
        description="NEFT CR-HDFC 260812345678 RAZORPAY",
        row_hash="hash_reg_d",
        batch_id=batch_id,
    )

    # 5. Category (e): Batched 3-item payout (25k + 35k + 40k = 100k)
    s_e1 = RazorpaySettlement(
        settlement_id="setl_reg_e1",
        amount=Decimal("25000.00"),
        gross_amount=Decimal("25000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="BTRIP_UTR_01",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={},
        is_test_mode=True,
    )
    s_e2 = RazorpaySettlement(
        settlement_id="setl_reg_e2",
        amount=Decimal("35000.00"),
        gross_amount=Decimal("35000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="BTRIP_UTR_02",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={},
        is_test_mode=True,
    )
    s_e3 = RazorpaySettlement(
        settlement_id="setl_reg_e3",
        amount=Decimal("40000.00"),
        gross_amount=Decimal("40000.00"),
        fees=Decimal("0.00"),
        tax=Decimal("0.00"),
        utr="BTRIP_UTR_03",
        status="processed",
        settlement_created_at=now - timedelta(days=6),
        raw_payload={},
        is_test_mode=True,
    )
    tx_e = BankTransaction(
        date=now - timedelta(days=6),
        amount=Decimal("100000.00"),
        direction="CREDIT",
        utr=None,
        description="DIRECT CR BATCH TRIPLET 100K",
        row_hash="hash_reg_e",
        batch_id=batch_id,
    )

    # 6. Category (f): Genuine Exception (unlinked external deposit > 5d old)
    tx_f = BankTransaction(
        date=now - timedelta(days=12),
        amount=Decimal("99999.00"),
        direction="CREDIT",
        utr="EXTERNAL_DIRECT_UTR_99",
        description="NON RAZORPAY EXTERNAL CLIENT DEPOSIT",
        row_hash="hash_reg_f",
        batch_id=batch_id,
    )

    all_settlements = [s_a, s_b, s_c, s_d, s_e1, s_e2, s_e3]
    all_bank_txs = [tx_a, tx_b, tx_c, tx_d, tx_e, tx_f]

    for s in all_settlements:
        db_session.add(s)
    for tx in all_bank_txs:
        db_session.add(tx)
    await db_session.commit()

    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    logs = await engine.reconcile_batch(
        bank_transactions=all_bank_txs,
        settlements=all_settlements,
        batch_id=batch_id,
    )
    await db_session.commit()

    log_map = {l.bank_tx_id: l for l in logs}

    # Verify Category (a) Refund match
    log_a = log_map[tx_a.id]
    assert log_a.match_status == "MATCHED"
    assert log_a.diagnostic_type == "REFUND_ADJUSTED"
    assert log_a.match_tier == "TIER_3"

    # Verify Category (b) Date window fallback match
    log_b = log_map[tx_b.id]
    assert log_b.match_status == "SUGGESTED"
    assert log_b.diagnostic_type == "DATE_AMOUNT_FALLBACK"
    assert log_b.match_tier == "TIER_0"

    # Verify Category (c) Gross vs Net fee deduction match
    log_c = log_map[tx_c.id]
    assert log_c.match_status == "MATCHED"
    assert log_c.diagnostic_type == "FEE_DEDUCTION"
    assert log_c.match_tier == "TIER_3"

    # Verify Category (d) Reference UTR normalization match
    log_d = log_map[tx_d.id]
    assert log_d.match_status == "MATCHED"
    assert log_d.diagnostic_type == "EXACT_MATCH"

    # Verify Category (e) 3-item Batched payout subset-sum match
    log_e = log_map[tx_e.id]
    assert log_e.match_status == "MATCHED"
    assert log_e.diagnostic_type == "BATCHED_SETTLEMENT"
    assert "3 batched Razorpay payouts" in log_e.diagnostic_note

    # Verify Category (f) Genuine Exception is preserved
    log_f = log_map[tx_f.id]
    assert log_f.match_status == "EXCEPTION"
    assert log_f.diagnostic_type == "UNRESOLVED"
    assert "No matching Razorpay settlement found" in log_f.diagnostic_note


@pytest.mark.asyncio
async def test_matching_engine_via_http_api_endpoints(db_session: AsyncSession):
    """Verifies that scorecard and status API endpoints return accurate metrics and conservation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Reset demo dataset
        reset_res = await client.post("/api/v1/demo/reset?batch_id=http_recon_test")
        assert reset_res.status_code == 200

        # 2. Seed realistic dataset
        seed_res = await client.post("/api/v1/demo/seed?count=60&batch_id=http_recon_test")
        assert seed_res.status_code == 200
        seed_data = seed_res.json()["data"]
        assert seed_data["total_settlements"] >= 60
        assert seed_data["total_bank_transactions"] >= 60

        # 3. Fetch summary status
        status_res = await client.get("/api/v1/reconciliation/http_recon_test/status")
        assert status_res.status_code == 200
        status_data = status_res.json()["data"]
        assert status_data["total_records"] >= 60
        assert status_data["match_rate_percentage"] > 80.0
        assert status_data["exception_count"] == 2  # Exactly the 2 seeded true exceptions

        # 4. Fetch audit-grade scorecard
        scorecard_res = await client.get("/api/v1/reconciliation/http_recon_test/scorecard")
        assert scorecard_res.status_code == 200
        sc_data = scorecard_res.json()["data"]
        assert sc_data["is_fully_accounted"] is True
        assert sc_data["unaccounted_records"] == 0
        assert sc_data["total_exception_count"] == 2
        assert len(sc_data["exceptions"]) == 2

        # 5. Fetch records with filter
        records_res = await client.get("/api/v1/reconciliation/http_recon_test/records?status=EXCEPTION")
        assert records_res.status_code == 200
        rec_data = records_res.json()["data"]
        assert rec_data["total_count"] == 2
