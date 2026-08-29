"""Unit tests for edge cases and multi-tier mechanics in ReconciliationEngine."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.bank_repo import BankRepository
from app.repositories.settlement_repo import SettlementRepository
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine


@pytest.mark.asyncio
async def test_reconciliation_conflict_detection(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # Two separate bank rows with the exact same UTR & amount
    tx1, _ = await bank_repo.upsert_transaction({
        "batch_id": "conflict_batch",
        "row_hash": "hash_conf_1",
        "date": dt,
        "amount": Decimal("50000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491901",
        "description": "CMS/002938491901/HDFC Entry 1",
    })

    tx2, _ = await bank_repo.upsert_transaction({
        "batch_id": "conflict_batch",
        "row_hash": "hash_conf_2",
        "date": dt,
        "amount": Decimal("50000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491901",
        "description": "CMS/002938491901/HDFC Entry 2",
    })

    # Single Razorpay settlement
    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_conf_001",
        "amount": Decimal("50000.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": "CMS002938491901",
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx1, tx2], [setl], batch_id="conflict_batch")
    assert len(logs) == 2
    # Both rows must be locked as CONFLICT
    assert all(l.match_status == "CONFLICT" for l in logs)
    assert all("Conflict: Settlement setl_conf_001 matches multiple bank rows" in l.diagnostic_note for l in logs)


@pytest.mark.asyncio
async def test_reconciliation_tier_0_fallback_missing_utr(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # Bank row without UTR
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "fallback_batch",
        "row_hash": "hash_fallback_1",
        "date": dt,
        "amount": Decimal("35000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "GENERIC CREDIT TRANSFER WITHOUT UTR",
    })

    # Settlement with date within 2 days and matching amount
    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_fallback_001",
        "amount": Decimal("35000.00"),
        "gross_amount": Decimal("35000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": "CMS_DIFFERENT_UTR",
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx], [setl], batch_id="fallback_batch")
    assert len(logs) == 1
    log = logs[0]
    assert log.match_tier == "TIER_0"
    assert log.match_status == "SUGGESTED"
    assert log.diagnostic_type == "DATE_AMOUNT_FALLBACK"


@pytest.mark.asyncio
async def test_reconciliation_batched_settlement_subset_sum(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # 1 Bank row for sum of 2 settlements: 20000 + 30000 = 50000
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "batched_batch",
        "row_hash": "hash_batch_sum_1",
        "date": dt,
        "amount": Decimal("50000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "BATCHED RAZORPAY SETTLEMENT PAYOUT",
    })

    setl1, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_batch_sub_01",
        "amount": Decimal("20000.00"),
        "gross_amount": Decimal("20000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    setl2, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_batch_sub_02",
        "amount": Decimal("30000.00"),
        "gross_amount": Decimal("30000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx], [setl1, setl2], batch_id="batched_batch")
    assert len(logs) == 1
    assert logs[0].match_status == "MATCHED"
    assert logs[0].diagnostic_type == "BATCHED_SETTLEMENT"
    assert "Batched Settlement Match" in logs[0].diagnostic_note


@pytest.mark.asyncio
async def test_competing_conflict_logs_retrieval(db_session: AsyncSession):
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    tx1, _ = await bank_repo.upsert_transaction({
        "batch_id": "comp_conflict_batch",
        "row_hash": "hash_comp_1",
        "date": dt,
        "amount": Decimal("50000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491902",
        "description": "CMS/002938491902/HDFC Branch 1",
    })

    tx2, _ = await bank_repo.upsert_transaction({
        "batch_id": "comp_conflict_batch",
        "row_hash": "hash_comp_2",
        "date": dt,
        "amount": Decimal("50000.00"),
        "direction": "CREDIT",
        "utr": "CMS002938491902",
        "description": "CMS/002938491902/HDFC Branch 2",
    })

    setl, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_comp_001",
        "amount": Decimal("50000.00"),
        "gross_amount": Decimal("50000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": "CMS002938491902",
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx1, tx2], [setl], batch_id="comp_conflict_batch")
    assert len(logs) == 2
    assert all(l.match_status == "CONFLICT" for l in logs)

    # Test get_competing_conflict_logs
    competing = await recon_repo.get_competing_conflict_logs(
        batch_id="comp_conflict_batch",
        settlement_db_id=setl.id,
        exclude_log_id=logs[0].id,
    )
    assert len(competing) == 1
    assert competing[0].id == logs[1].id

