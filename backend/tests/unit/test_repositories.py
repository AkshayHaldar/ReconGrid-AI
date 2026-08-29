"""Unit tests for the repository query layer (Bank, Settlement, Reconciliation, QA)."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.bank_repo import BankRepository
from app.repositories.settlement_repo import SettlementRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.repositories.qa_repo import QaRepository


@pytest.mark.asyncio
async def test_bank_repository_crud(db_session: AsyncSession):
    repo = BankRepository(db_session)
    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # Upsert new transaction
    tx_data = {
        "batch_id": "batch_repo_test",
        "row_hash": "hash_1234567890abcdef",
        "date": dt,
        "amount": Decimal("15000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491999",
        "description": "CMS/002938491999/HDFC",
        "raw_csv_row": {"sample": "val"},
    }
    tx, created = await repo.upsert_transaction(tx_data)
    assert created is True
    assert tx.id is not None
    assert tx.amount == Decimal("15000.00")

    # Upsert same transaction (idempotent)
    tx2, created2 = await repo.upsert_transaction(tx_data)
    assert created2 is False
    assert tx2.id == tx.id

    # Lookup by ID and Hash
    found_by_id = await repo.get_by_id(tx.id)
    assert found_by_id is not None
    assert found_by_id.row_hash == "hash_1234567890abcdef"

    found_by_hash = await repo.get_by_row_hash("hash_1234567890abcdef")
    assert found_by_hash is not None
    assert found_by_hash.id == tx.id

    # Nonexistent
    assert await repo.get_by_id("nonexistent_id") is None
    assert await repo.get_by_row_hash("nonexistent_hash") is None

    # Get all by batch
    all_batch = await repo.get_all_by_batch("batch_repo_test")
    assert len(all_batch) == 1

    unrec = await repo.get_unreconciled_or_all("batch_repo_test")
    assert len(unrec) == 1


@pytest.mark.asyncio
async def test_settlement_repository_crud(db_session: AsyncSession):
    repo = SettlementRepository(db_session)
    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    setl_data = {
        "settlement_id": "setl_repo_test_001",
        "amount": Decimal("49100.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("762.71"),
        "tax": Decimal("137.29"),
        "utr": "CMS002938491805",
        "status": "processed",
        "settlement_created_at": dt,
        "raw_payload": {"description": "test settlement payload"},
    }

    setl, created = await repo.upsert_settlement(setl_data)
    assert created is True
    assert setl.id is not None

    # Update existing settlement
    setl_data["status"] = "settled"
    updated_setl, created2 = await repo.upsert_settlement(setl_data)
    assert created2 is False
    assert updated_setl.status == "settled"

    # Lookup by settlement_id & db_id
    found_by_setl_id = await repo.get_by_settlement_id("setl_repo_test_001")
    assert found_by_setl_id is not None
    assert found_by_setl_id.id == setl.id

    found_by_db_id = await repo.get_by_id(setl.id)
    assert found_by_db_id is not None
    assert found_by_db_id.settlement_id == "setl_repo_test_001"

    # Get all settlements
    all_setls = await repo.get_all()
    assert len(all_setls) >= 1

    # Nonexistent
    assert await repo.get_by_settlement_id("setl_nonexistent") is None
    assert await repo.get_by_id("nonexistent_id") is None


@pytest.mark.asyncio
async def test_reconciliation_repository_ledger_and_metrics(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # 1. Create bank tx & settlement
    bank_tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "batch_metrics_test",
        "row_hash": "hash_metrics_test_01",
        "date": dt,
        "amount": Decimal("98200.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491801",
        "description": "CMS/002938491801/HDFC",
    })

    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_metrics_test_01",
        "amount": Decimal("98200.00"),
        "gross_amount": Decimal("98200.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": "CMS002938491801",
        "status": "processed",
        "settlement_created_at": dt,
    })

    # 2. Add log
    log = await recon_repo.add_log({
        "batch_id": "batch_metrics_test",
        "bank_tx_id": bank_tx.id,
        "rzp_settlement_id": setl.id,
        "match_status": "MATCHED",
        "match_tier": "TIER_1",
        "confidence_score": 1.00,
        "delta_amount": Decimal("0.00"),
        "diagnostic_type": "EXACT_MATCH",
        "diagnostic_note": "Exact match test",
        "matched_at": dt,
        "superseded": False,
    })
    assert log.id is not None

    # Lookup by ID
    found_log = await recon_repo.get_by_id(log.id)
    assert found_log is not None
    assert found_log.bank_transaction.amount == Decimal("98200.00")

    # Get active logs with filter and search
    logs, count = await recon_repo.get_active_logs(
        batch_id="batch_metrics_test",
        status_filter="MATCHED",
        search="CMS002938491801",
    )
    assert count == 1
    assert len(logs) == 1

    # Get summary metrics
    metrics = await recon_repo.get_summary_metrics(batch_id="batch_metrics_test")
    assert metrics["total_records"] == 1
    assert metrics["matched_count"] == 1
    assert metrics["match_rate_percentage"] == 100.0
    assert metrics["total_reconciled_amount"] == Decimal("98200.00")

    # Test supersede
    await recon_repo.supersede_previous_logs(bank_tx.id)
    logs_after_supersede, count_after = await recon_repo.get_active_logs(batch_id="batch_metrics_test")
    assert count_after == 0


@pytest.mark.asyncio
async def test_qa_repository_and_retrieval(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    qa_repo = QaRepository(db_session)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    bank_tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "batch_qa_test",
        "row_hash": "hash_qa_test_01",
        "date": dt,
        "amount": Decimal("49100.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491805",
        "description": "CMS/002938491805/RAZORPAY order #4521",
    })

    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_Kjs9283jkd922",
        "amount": Decimal("49100.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("762.71"),
        "tax": Decimal("137.29"),
        "utr": "CMS002938491805",
        "status": "processed",
        "settlement_created_at": dt,
    })

    log = await recon_repo.add_log({
        "batch_id": "batch_qa_test",
        "bank_tx_id": bank_tx.id,
        "rzp_settlement_id": setl.id,
        "match_status": "MATCHED",
        "match_tier": "TIER_3",
        "confidence_score": 1.00,
        "delta_amount": Decimal("900.00"),
        "diagnostic_type": "FEE_DEDUCTION",
        "diagnostic_note": "Gateway fee Rs 762.71 + 18% GST Rs 137.29",
        "matched_at": dt,
        "superseded": False,
    })

    # Search by settlement ID
    rec1 = await qa_repo.find_reconciliation_record("Why did setl_Kjs9283jkd922 have a fee deduction?")
    assert rec1 is not None
    assert rec1.id == log.id

    # Search by UTR / description token
    rec2 = await qa_repo.find_reconciliation_record("What happened with CMS002938491805?")
    assert rec2 is not None
    assert rec2.id == log.id

    # Search non-existent
    assert await qa_repo.find_reconciliation_record("nonexistent_token_99999") is None

    # Log interaction
    qa_log = await qa_repo.log_interaction({
        "reconciliation_log_id": log.id,
        "query_text": "What happened with CMS002938491805?",
        "raw_llm_output": "Narration text",
        "final_response": "Narration text",
        "guardrail_rejected": False,
        "asked_at": dt,
    })
    assert qa_log.id is not None

    history = await qa_repo.get_history(limit=10)
    assert len(history) >= 1
