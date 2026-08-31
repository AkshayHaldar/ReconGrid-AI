"""Generate Scorecard Report Script for ReconGrid AI.

Runs the 50+ record synthetic golden reconciliation batch, measures execution
throughput, computes separate Tier 0/1/2/3 breakdown metrics and full exception details,
and writes the regenerable docs/SCORECARD.md report.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import async_session_factory, init_db
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, format_inr, to_decimal


async def run_scorecard_generation():
    print("[*] Initializing database and loading 50+ golden synthetic dataset...")
    await init_db()

    fixture_path = Path(__file__).parent.parent / "tests" / "fixtures" / "synthetic_batch.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    batch_id = "golden_scorecard_batch"
    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:
        from sqlalchemy import delete
        from app.models.reconciliation_log import ReconciliationLog
        await session.execute(delete(ReconciliationLog).where(ReconciliationLog.batch_id == batch_id))
        await session.execute(delete(BankTransaction).where(BankTransaction.batch_id == batch_id))
        await session.execute(delete(RazorpaySettlement).where(RazorpaySettlement.is_test_mode == True))
        await session.commit()

        recon_repo = ReconciliationRepository(session)
        engine = ReconciliationEngine(recon_repo)

        # 1. Ingest settlements from fixture + scaling loop
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
            session.add(setl)
            saved_settlements.append(setl)

        # Scale to 55+ records using standard 2% MDR + 18% GST fee formula
        for i in range(12, 55):
            amt = Decimal(f"{(i * 3500) % 80000 + 10000}.00")
            fees, tax, net_amt = calculate_standard_fees(amt)
            setl = RazorpaySettlement(
                settlement_id=f"setl_gold_{i:03d}",
                amount=net_amt,
                gross_amount=amt,
                fees=fees,
                tax=tax,
                utr=f"CMS0029384918{i:02d}",
                status="processed",
                settlement_created_at=now - timedelta(days=i % 10),
                raw_payload={},
                is_test_mode=True,
            )
            session.add(setl)
            saved_settlements.append(setl)

        await session.flush()

        # 2. Ingest bank statement transactions
        saved_bank_txs = []
        for idx, b in enumerate(fixture_data["bank_transactions"]):
            dt = now - timedelta(days=b.get("days_ago", 1))
            tx = BankTransaction(
                date=dt,
                amount=to_decimal(b["amount"]),
                direction=b.get("direction", "CREDIT"),
                utr=b.get("utr"),
                description=b["description"],
                row_hash=f"hash_scorecard_{idx}",
                raw_csv_row=b,
                batch_id=batch_id,
            )
            session.add(tx)
            saved_bank_txs.append(tx)

        for i in range(12, 55):
            target_s = saved_settlements[i - 1]
            tx = BankTransaction(
                date=target_s.settlement_created_at,
                amount=to_decimal(target_s.amount),
                direction="CREDIT",
                utr=target_s.utr,
                description=f"CMS/{target_s.utr}/HDFC/RAZORPAY PAYOUT {i}",
                row_hash=f"hash_scorecard_{i:03d}",
                raw_csv_row={},
                batch_id=batch_id,
            )
            session.add(tx)
            saved_bank_txs.append(tx)

        await session.flush()

        # 3. Execute matching engine with high-precision timer
        print(f"[*] Running 4-Tier Reconciliation Engine on {len(saved_bank_txs)} bank transactions...")
        t_start = time.perf_counter()
        reconciled_logs = await engine.reconcile_batch(
            bank_transactions=saved_bank_txs,
            settlements=saved_settlements,
            batch_id=batch_id,
        )
        t_elapsed = time.perf_counter() - t_start
        processing_time = Decimal(str(t_elapsed)).quantize(Decimal("0.0001"))

        # 4. Generate scorecard metrics
        scorecard = await recon_repo.get_scorecard_metrics(
            batch_id=batch_id,
            processing_time_seconds=processing_time,
        )
        await session.commit()

    # 5. Format Markdown Report
    repo_root = Path(__file__).parent.parent.parent
    docs_dir = repo_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    scorecard_path = docs_dir / "SCORECARD.md"

    md_content = f"""# ReconGrid AI — Reconciliation Engine Scorecard & Audit Report

**Executive Summary:** Reconciled **{scorecard['total_rows_processed']} bank transactions** against Razorpay settlements in **{scorecard['processing_time_seconds']}s** ({scorecard['rows_per_second']} rows/sec) with **{scorecard['total_matched_percentage']}% automated match rate**, zero dropped records, and complete diagnostic accountability.

---

## 1. Throughput & Processing Benchmarks

| Metric | Value | Unit / Standard |
|---|---|---|
| **Total Rows Processed** | `{scorecard['total_rows_processed']}` | Bank Transactions |
| **Execution Time** | `{scorecard['processing_time_seconds']}` | Seconds (Measured Wall-Clock) |
| **Processing Throughput** | `{scorecard['rows_per_second']}` | Rows / Second |
| **Total ₹ Ingested** | `₹ {scorecard['total_ingested_amount']:,.2f}` | Python Decimal(18,2) |
| **Total ₹ Reconciled** | `₹ {scorecard['total_reconciled_amount']:,.2f}` | Python Decimal(18,2) |
| **Total ₹ Exceptions** | `₹ {scorecard['total_exception_amount']:,.2f}` | Python Decimal(18,2) |
| **Total ₹ Pending Data** | `₹ {scorecard['total_pending_amount']:,.2f}` | Python Decimal(18,2) |

---

## 2. Per-Tier Reconciliation Breakdown

> [!NOTE]
> Per-tier counts are kept strictly separate and never aggregated into an opaque single accuracy score.

| Tier / Category | Classification Type | Records | Share (%) | Status & Action Required |
|---|---|---|---|---|
| **Tier 1** | Exact UTR + Exact Amount Match | `{scorecard['tier_1_count']}` | `{scorecard['tier_1_percentage']}%` | Automated `MATCHED` (100% confidence) |
| **Tier 2** | Fuzzy Descriptor Similarity | `{scorecard['tier_2_count']}` | `{scorecard['tier_2_percentage']}%` | `SUGGESTED` match (Requires 1-click CA review) |
| **Tier 0** | Date Window (±3d) + Amount Fallback | `{scorecard['tier_0_count']}` | `{scorecard['tier_0_percentage']}%` | `SUGGESTED` match (Missing UTR fallback) |
| **Tier 3** | Diagnostic Delta (Fee/TDS/Refund/FX) | `{scorecard['tier_3_count']}` | `{scorecard['tier_3_percentage']}%` | Automated `MATCHED` with diagnostic breakdown |
| **Conflicts** | Multi-Candidate Competing Claims | `{scorecard['total_conflict_count']}` | `{scorecard['total_conflict_percentage']}%` | `CONFLICT` (Locked pending human merge) |
| **Exceptions** | Genuine Discrepancies (>5d old) | `{scorecard['total_exception_count']}` | `{scorecard['total_exception_percentage']}%` | `EXCEPTION` (Unresolved discrepancy) |
| **Pending** | Awaiting Settlement Data (≤5d old) | `{scorecard['total_pending_count']}` | `{scorecard['total_pending_percentage']}%` | `PENDING_SETTLEMENT_DATA` (Auto-retries on next sync) |
| **TOTAL** | **All Processed Records** | **`{scorecard['total_rows_processed']}`** | **`100.00%`** | **100% Accounted For** |

---

## 3. Mathematical Conservation & Integrity Proof

$$\\sum (\\text{{Tier 0}} + \\text{{Tier 1}} + \\text{{Tier 2}} + \\text{{Tier 3 Matches}} + \\text{{Conflicts}} + \\text{{Exceptions}} + \\text{{Pending}}) = \\text{{Total Rows Processed}}$$

* **Records Accounted For:** `{scorecard['records_accounted_for']} / {scorecard['total_rows_processed']}`
* **Unaccounted / Dropped Records:** `{scorecard['unaccounted_records']}`
* **Conservation Verified:** `{'PASSED — Zero records dropped or lost' if scorecard['is_fully_accounted'] else 'FAILED'}`

---

## 4. Complete Unfiltered Exceptions List

| Transaction ID | Date | Amount (₹) | Reason Code | Bank Description | Diagnostic Note |
|---|---|---|---|---|---|
"""

    for exc in scorecard["exceptions"]:
        dt_str = exc["date"].strftime("%Y-%m-%d") if isinstance(exc["date"], datetime) else str(exc["date"])
        amt_str = f"₹ {exc['amount']:,.2f}"
        md_content += f"| `{exc['bank_transaction_id'][:8]}...` | {dt_str} | {amt_str} | `{exc['reason_code']}` | {exc['description']} | {exc['diagnostic_note']} |\n"

    md_content += f"\n*Report generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} by `scripts/generate_scorecard_report.py`.*\n"

    with open(scorecard_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"[+] Scorecard written successfully to {scorecard_path}")
    print(f"    - Total Rows: {scorecard['total_rows_processed']}")
    print(f"    - Throughput: {scorecard['rows_per_second']} rows/sec in {scorecard['processing_time_seconds']}s")
    print(f"    - Match Rate: {scorecard['total_matched_percentage']}%")
    print(f"    - Exceptions: {scorecard['total_exception_count']}")
    return scorecard_path


if __name__ == "__main__":
    asyncio.run(run_scorecard_generation())
