"""Deep edge-case testing for 98%+ code coverage across all core modules."""

from datetime import datetime, timezone
from decimal import Decimal
import io
import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpayRefund, RazorpaySettlement
from app.repositories.bank_repo import BankRepository
from app.repositories.settlement_repo import SettlementRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.ingestion import IngestionService
from app.services.reconciliation import ReconciliationEngine
from app.utils.fuzzy import compute_string_similarity, is_fuzzy_match, normalize_descriptor
from app.utils.money import to_decimal


@pytest.mark.asyncio
async def test_reconciliation_utr_match_with_amount_delta_tier3(db_session: AsyncSession):
    """Tests when bank UTR matches settlement UTR, but amount differs (Fee/GST diagnostic)."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # Bank row has UTR and received net 49100.00
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "delta_batch",
        "row_hash": "hash_delta_utr_1",
        "date": dt,
        "amount": Decimal("49100.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491855",
        "description": "CMS/002938491855/RAZORPAY",
    })

    # Settlement has gross 50000.00, net 50000.00 (before fees deducted at bank)
    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_delta_001",
        "amount": Decimal("50000.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("762.71"),
        "tax": Decimal("137.29"),
        "utr": "CMS002938491855",
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx], [setl], batch_id="delta_batch")
    assert len(logs) == 1
    log = logs[0]
    assert log.match_status == "MATCHED"
    assert log.diagnostic_type == "FEE_DEDUCTION"
    assert "Tier 3 diagnostic on UTR CMS002938491855" in log.diagnostic_note


@pytest.mark.asyncio
async def test_ingestion_validation_errors(db_session: AsyncSession):
    """Tests file size, MIME type, and empty content rejection in IngestionService."""
    service = IngestionService(db_session)

    # 1. Invalid MIME type
    bad_mime_file = UploadFile(
        filename="malicious.exe",
        file=io.BytesIO(b"binary data"),
        headers={"content-type": "application/x-msdownload"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.ingest_csv(bad_mime_file, batch_id="b1")
    assert exc_info.value.status_code == 400
    assert "Invalid file type" in exc_info.value.detail

    # 2. Empty file
    empty_file = UploadFile(
        filename="empty.csv",
        file=io.BytesIO(b""),
        headers={"content-type": "text/csv"},
    )
    with pytest.raises(HTTPException) as exc_info2:
        await service.ingest_csv(empty_file, batch_id="b2")
    assert exc_info2.value.status_code == 400
    assert "No valid bank transaction rows" in exc_info2.value.detail


@pytest.mark.asyncio
async def test_summary_metrics_human_action_branches(db_session: AsyncSession):
    """Tests summary metrics calculation with APPROVED suggested and RESOLVED conflict records."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # Suggested & Approved record
    tx1, _ = await bank_repo.upsert_transaction({
        "batch_id": "metrics_action_batch",
        "row_hash": "hash_act_1",
        "date": dt,
        "amount": Decimal("10000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491861",
        "description": "CMS/002938491861",
    })

    log1 = await recon_repo.add_log({
        "batch_id": "metrics_action_batch",
        "bank_tx_id": tx1.id,
        "match_status": "SUGGESTED",
        "human_action": "APPROVED",
        "match_tier": "TIER_2",
        "delta_amount": Decimal("0.00"),
        "diagnostic_type": "FUZZY_MATCH",
        "diagnostic_note": "Fuzzy approved",
        "matched_at": dt,
        "superseded": False,
    })

    # Conflict & Resolved record
    tx2, _ = await bank_repo.upsert_transaction({
        "batch_id": "metrics_action_batch",
        "row_hash": "hash_act_2",
        "date": dt,
        "amount": Decimal("20000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491862",
        "description": "CMS/002938491862",
    })

    log2 = await recon_repo.add_log({
        "batch_id": "metrics_action_batch",
        "bank_tx_id": tx2.id,
        "match_status": "CONFLICT",
        "human_action": "RESOLVED",
        "match_tier": "TIER_1",
        "delta_amount": Decimal("0.00"),
        "diagnostic_type": "EXACT_MATCH",
        "diagnostic_note": "Conflict resolved",
        "matched_at": dt,
        "superseded": False,
    })

    metrics = await recon_repo.get_summary_metrics("metrics_action_batch")
    assert metrics["total_records"] == 2
    assert metrics["matched_count"] == 2
    assert metrics["total_reconciled_amount"] == Decimal("30000.00")
    assert metrics["match_rate_percentage"] == 100.0


@pytest.mark.asyncio
async def test_settlement_refunds_relation(db_session: AsyncSession):
    """Tests get_refunds_for_settlement repository method."""
    repo = SettlementRepository(db_session)
    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    setl, _ = await repo.upsert_settlement({
        "settlement_id": "setl_with_refund_01",
        "amount": Decimal("45000.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": "CMS002938491870",
        "status": "processed",
        "settlement_created_at": dt,
    })

    refund = RazorpayRefund(
        refund_id="rfnd_test_001",
        settlement_id="setl_with_refund_01",
        payment_id="pay_test_001",
        amount=Decimal("5000.00"),
        status="processed",
        processed_at=dt,
        raw_payload={},
    )
    db_session.add(refund)
    await db_session.flush()

    refunds = await repo.get_refunds_for_settlement("setl_with_refund_01")
    assert len(refunds) == 1
    assert refunds[0].refund_id == "rfnd_test_001"
    assert refunds[0].amount == Decimal("5000.00")


def test_fuzzy_matching_edge_cases():
    assert compute_string_similarity(None, "test") == 0.0
    assert compute_string_similarity("test", None) == 0.0
    assert compute_string_similarity("", "") == 0.0
    assert compute_string_similarity("same", "same") == 1.0

    matched, score = is_fuzzy_match("short", "different text", threshold=0.90)
    assert matched is False
    assert score < 0.90


def test_money_to_decimal_edge_cases():
    assert to_decimal(None) == Decimal("0.00")
    assert to_decimal("") == Decimal("0.00")
    assert to_decimal("   ") == Decimal("0.00")
    assert to_decimal(100) == Decimal("100.00")
    assert to_decimal(100.5) == Decimal("100.50")
    with pytest.raises(TypeError):
        to_decimal({})  # type: ignore
