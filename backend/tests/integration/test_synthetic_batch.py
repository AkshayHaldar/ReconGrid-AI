"""Integration test running the full reconciliation pipeline on the 50+ golden synthetic dataset."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import format_inr, to_decimal


@pytest.mark.asyncio
async def test_golden_synthetic_batch(db_session: AsyncSession):
    fixture_path = Path(__file__).parent.parent / "fixtures" / "synthetic_batch.json"
    assert fixture_path.exists(), "synthetic_batch.json fixture must exist"

    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    now = datetime.now(timezone.utc)
    recon_repo = ReconciliationRepository(db_session)
    engine = ReconciliationEngine(recon_repo)

    # 1. Ingest settlements
    saved_settlements = []
    for s in fixture_data["settlements"]:
        dt = now - timedelta(days=s.get("days_ago", 1))
        setl = RazorpaySettlement(
            settlement_id=s["settlement_id"],
            amount=to_decimal(s["amount"]),
            gross_amount=to_decimal(s["gross_amount"]),
            fees=to_decimal(s["fees"]),
            tax=to_decimal(s["tax"]),
            utr=s.get("utr"),
            status=s.get("status", "processed"),
            settlement_created_at=dt,
            raw_payload=s.get("payload", {}),
            is_test_mode=True,
        )
        db_session.add(setl)
        saved_settlements.append(setl)

    # Add extra settlements to ensure scale >= 50
    for i in range(12, 55):
        amt = Decimal(f"{(i * 3500) % 80000 + 10000}.00")
        fees = (amt * Decimal("0.015")).quantize(Decimal("0.01"))
        tax = (fees * Decimal("0.18")).quantize(Decimal("0.01"))
        setl = RazorpaySettlement(
            settlement_id=f"setl_gold_{i:03d}",
            amount=amt - fees - tax,
            gross_amount=amt,
            fees=fees,
            tax=tax,
            utr=f"CMS0029384918{i:02d}",
            status="processed",
            settlement_created_at=now - timedelta(days=i % 10),
            raw_payload={},
            is_test_mode=True,
        )
        db_session.add(setl)
        saved_settlements.append(setl)

    await db_session.flush()

    # 2. Ingest bank transactions
    saved_bank_txs = []
    for idx, b in enumerate(fixture_data["bank_transactions"]):
        dt = now - timedelta(days=b.get("days_ago", 1))
        tx = BankTransaction(
            date=dt,
            amount=to_decimal(b["amount"]),
            direction=b.get("direction", "CREDIT"),
            utr=b.get("utr"),
            description=b["description"],
            row_hash=f"hash_test_gold_{idx}",
            raw_csv_row=b,
            batch_id="golden_batch",
        )
        db_session.add(tx)
        saved_bank_txs.append(tx)

    # Add matching bank transactions for extra settlements
    for i in range(12, 55):
        target_s = saved_settlements[i - 1]
        tx = BankTransaction(
            date=target_s.settlement_created_at,
            amount=to_decimal(target_s.amount),
            direction="CREDIT",
            utr=target_s.utr,
            description=f"CMS/{target_s.utr}/HDFC/RAZORPAY PAYOUT {i}",
            row_hash=f"hash_test_gold_{i:03d}",
            raw_csv_row={},
            batch_id="golden_batch",
        )
        db_session.add(tx)
        saved_bank_txs.append(tx)

    await db_session.flush()

    # 3. Run reconciliation engine
    reconciled_logs = await engine.reconcile_batch(
        bank_transactions=saved_bank_txs,
        settlements=saved_settlements,
        batch_id="golden_batch",
    )

    summary = await recon_repo.get_summary_metrics("golden_batch")

    # 4. Assertions on success metrics
    assert summary["total_records"] >= 50, f"Expected >= 50 records, got {summary['total_records']}"
    assert summary["match_rate_percentage"] >= 85.0, (
        f"Expected match rate >= 85%, got {summary['match_rate_percentage']}%"
    )
    assert summary["matched_count"] > 0
    assert summary["suggested_count"] > 0, "Suggested matches must be identified"
    assert summary["conflict_count"] > 0, "Conflicts must be detected"
    assert summary["exception_count"] > 0, "Exceptions must be caught and preserved"
    assert summary["total_reconciled_amount"] > Decimal("0.00")
    assert summary["total_ingested_amount"] > summary["total_reconciled_amount"]

    # Verify that exceptions have honest, non-empty reason notes
    for log in reconciled_logs:
        if log.match_status == "EXCEPTION":
            assert len(log.diagnostic_note) > 5
            assert log.diagnostic_type == "UNRESOLVED"
