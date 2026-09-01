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


@pytest.mark.asyncio
async def test_reconciliation_batched_triplet_subset_sum(db_session: AsyncSession):
    """Tests clean triplet (k=3) batched settlement subset-sum match."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    dt = datetime(2026, 8, 24, tzinfo=timezone.utc)

    # 1 Bank row for sum of 3 settlements: 15k + 25k + 35k = 75k
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "triplet_batch",
        "row_hash": "hash_trip_1",
        "date": dt,
        "amount": Decimal("75000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "DIRECT CR 3-WAY BATCH 75K",
    })

    setl1, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_trip_01",
        "amount": Decimal("15000.00"),
        "gross_amount": Decimal("15000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    setl2, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_trip_02",
        "amount": Decimal("25000.00"),
        "gross_amount": Decimal("25000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    setl3, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_trip_03",
        "amount": Decimal("35000.00"),
        "gross_amount": Decimal("35000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx], [setl1, setl2, setl3], batch_id="triplet_batch")
    assert len(logs) == 1
    assert logs[0].match_status == "MATCHED"
    assert logs[0].diagnostic_type == "BATCHED_SETTLEMENT"
    assert "3 batched Razorpay payouts" in logs[0].diagnostic_note


@pytest.mark.asyncio
async def test_reconciliation_batched_no_valid_subset_fallthrough(db_session: AsyncSession):
    """Tests when settlements exist < bank amount, but no subset sums to bank amount."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # Bank date > 5 days ago to avoid PENDING_SETTLEMENT_DATA
    dt = datetime(2026, 8, 10, tzinfo=timezone.utc)

    # Bank row 90,000.00
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "no_subset_batch",
        "row_hash": "hash_no_subset_1",
        "date": dt,
        "amount": Decimal("90000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "DIRECT CR NO SUBSET MATCH",
    })

    # Settlements: 20k + 30k = 50k (no combination reaches 90k)
    setl1, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_nosub_01",
        "amount": Decimal("20000.00"),
        "gross_amount": Decimal("20000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })
    setl2, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_nosub_02",
        "amount": Decimal("30000.00"),
        "gross_amount": Decimal("30000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    logs = await engine.reconcile_batch([tx], [setl1, setl2], batch_id="no_subset_batch")
    assert len(logs) == 1
    assert logs[0].match_status == "EXCEPTION"
    assert logs[0].diagnostic_type == "UNRESOLVED"


@pytest.mark.asyncio
async def test_reconciliation_batched_candidate_cap_boundary(db_session: AsyncSession):
    """Tests batched settlement when candidate pool exceeds the 40-candidate boundary."""
    bank_repo = BankRepository(db_session)
    setl_repo = SettlementRepository(db_session)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # Bank date > 5 days ago to avoid PENDING_SETTLEMENT_DATA
    dt = datetime(2026, 8, 10, tzinfo=timezone.utc)

    # Bank row 60,000.00
    tx, _ = await bank_repo.upsert_transaction({
        "batch_id": "cap_batch",
        "row_hash": "hash_cap_1",
        "date": dt,
        "amount": Decimal("60000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "DIRECT CR CAP BOUNDARY TEST",
    })

    # 1. Two target settlements (25k + 35k = 60k) created at exact tx date dt (diff = 0)
    s_target1, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_cap_target_1",
        "amount": Decimal("25000.00"),
        "gross_amount": Decimal("25000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })
    s_target2, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_cap_target_2",
        "amount": Decimal("35000.00"),
        "gross_amount": Decimal("35000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt,
    })

    # 2. 35 noise settlements created 1 hour later (diff = 1h)
    from datetime import timedelta
    noise_close = []
    for i in range(35):
        s, _ = await setl_repo.upsert_settlement({
            "settlement_id": f"setl_noise_close_{i:03d}",
            "amount": Decimal("1000.00"),
            "gross_amount": Decimal("1000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": None,
            "status": "processed",
            "settlement_created_at": dt + timedelta(hours=1),
        })
        noise_close.append(s)

    # 3. 15 distant noise settlements created 2 days later (diff = 48h) — these will be truncated past the 40-cap
    noise_distant = []
    for i in range(15):
        s, _ = await setl_repo.upsert_settlement({
            "settlement_id": f"setl_noise_dist_{i:03d}",
            "amount": Decimal("1000.00"),
            "gross_amount": Decimal("1000.00"),
            "fees": Decimal("0.00"),
            "tax": Decimal("0.00"),
            "utr": None,
            "status": "processed",
            "settlement_created_at": dt + timedelta(days=2),
        })
        noise_distant.append(s)

    all_settlements = [s_target1, s_target2] + noise_close + noise_distant  # 52 total candidates
    logs = await engine.reconcile_batch([tx], all_settlements, batch_id="cap_batch")
    assert len(logs) == 1
    # Targets were within the top 40 candidates (rank 1 & 2 by time proximity), so they match
    assert logs[0].match_status == "MATCHED"
    assert logs[0].diagnostic_type == "BATCHED_SETTLEMENT"

    # Now verify that when 45 closer noise items push the target pair beyond the 40-cap, it falls through
    tx_blocked, _ = await bank_repo.upsert_transaction({
        "batch_id": "cap_batch_blocked",
        "row_hash": "hash_cap_blocked",
        "date": dt,
        "amount": Decimal("60000.00"),
        "direction": "CREDIT",
        "utr": None,
        "description": "DIRECT CR CAP BLOCKED TEST",
    })
    # Target pair is 3 days away (diff = 72h)
    s_far1, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_far_target_1",
        "amount": Decimal("25000.00"),
        "gross_amount": Decimal("25000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt + timedelta(days=3),
    })
    s_far2, _ = await setl_repo.upsert_settlement({
        "settlement_id": "setl_far_target_2",
        "amount": Decimal("35000.00"),
        "gross_amount": Decimal("35000.00"),
        "fees": Decimal("0.00"),
        "tax": Decimal("0.00"),
        "utr": None,
        "status": "processed",
        "settlement_created_at": dt + timedelta(days=3),
    })
    # 45 noise items are at dt (diff = 0), so they fill the entire 40-candidate window
    blocked_pool = noise_close + noise_distant[:10] + [s_far1, s_far2]
    logs_blocked = await engine.reconcile_batch([tx_blocked], blocked_pool, batch_id="cap_batch_blocked")
    assert len(logs_blocked) == 1
    # Distant targets are truncated out by the 40-candidate cap, cleanly falling through to EXCEPTION
    assert logs_blocked[0].match_status == "EXCEPTION"



