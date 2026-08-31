"""Benchmark Throughput Script for ReconGrid AI.

Benchmarks the full reconciliation engine pipeline on synthetic batches of
50, 200, 500, 1,000, and 5,000 record pairs.
Measures wall-clock time, rows/sec throughput, peak memory usage, match rate,
and mathematical conservation.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from pathlib import Path
import sys
import time
import tracemalloc

# Ensure backend root is on sys.path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.database import async_session_factory, init_db
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.repositories.reconciliation_repo import ReconciliationRepository
from app.services.reconciliation import ReconciliationEngine
from app.utils.money import calculate_standard_fees, format_inr, to_decimal


async def run_single_benchmark(batch_size: int) -> dict:
    batch_id = f"bench_batch_{batch_size}"
    now = datetime.now(timezone.utc)

    tracemalloc.start()
    mem_before, _ = tracemalloc.get_traced_memory()

    async with async_session_factory() as session:
        from sqlalchemy import delete
        await session.execute(delete(ReconciliationLog).where(ReconciliationLog.batch_id == batch_id))
        await session.execute(delete(BankTransaction).where(BankTransaction.batch_id == batch_id))
        await session.execute(delete(RazorpaySettlement).where(RazorpaySettlement.is_test_mode == True))
        await session.commit()

        recon_repo = ReconciliationRepository(session)
        engine = ReconciliationEngine(recon_repo)

        # 1. Generate settlements
        saved_settlements: list[RazorpaySettlement] = []
        for i in range(1, batch_size + 1):
            amt = Decimal(f"{(i * 3750) % 85000 + 10000}.00")
            fees, tax, net_amt = calculate_standard_fees(amt)
            s = RazorpaySettlement(
                settlement_id=f"setl_bench_{batch_size}_{i:05d}",
                amount=net_amt,
                gross_amount=amt,
                fees=fees,
                tax=tax,
                utr=f"CMS009988{batch_size}_{i:05d}",
                status="processed",
                settlement_created_at=now - timedelta(days=(i % 10) + 1),
                raw_payload={"description": f"Benchmark settlement {i}"},
                is_test_mode=True,
            )
            session.add(s)
            saved_settlements.append(s)
        await session.flush()

        # 2. Generate paired bank transactions (with 90% exact UTR, 5% fee/refund delta, 5% true exception)
        saved_bank_txs: list[BankTransaction] = []
        for i in range(1, batch_size + 1):
            target_s = saved_settlements[i - 1]
            if i % 20 == 0:
                # 5% True Exceptions (unlinked external deposit > 5d old)
                tx = BankTransaction(
                    date=now - timedelta(days=12),
                    amount=Decimal("49999.00"),
                    direction="CREDIT",
                    utr=f"EXT_NON_RZP_{batch_size}_{i:05d}",
                    description=f"EXTERNAL DIRECT CLIENT DEPOSIT {i}",
                    row_hash=f"hash_bench_{batch_size}_{i:05d}",
                    raw_csv_row={},
                    batch_id=batch_id,
                )
            elif i % 20 == 1:
                # 5% Fee deduction delta (bank received net against gross)
                tx = BankTransaction(
                    date=target_s.settlement_created_at,
                    amount=to_decimal(target_s.amount),
                    direction="CREDIT",
                    utr=target_s.utr,
                    description=f"CMS/{target_s.utr}/HDFC/FEE NET PAYOUT {i}",
                    row_hash=f"hash_bench_{batch_size}_{i:05d}",
                    raw_csv_row={},
                    batch_id=batch_id,
                )
            else:
                # 90% Clean exact UTR match
                tx = BankTransaction(
                    date=target_s.settlement_created_at,
                    amount=to_decimal(target_s.amount),
                    direction="CREDIT",
                    utr=target_s.utr,
                    description=f"CMS/{target_s.utr}/HDFC/RAZORPAY PAYOUT {i}",
                    row_hash=f"hash_bench_{batch_size}_{i:05d}",
                    raw_csv_row={},
                    batch_id=batch_id,
                )
            session.add(tx)
            saved_bank_txs.append(tx)
        await session.flush()

        # 3. Execute matching engine with wall-clock timer
        t_start = time.perf_counter()
        reconciled_logs = await engine.reconcile_batch(
            bank_transactions=saved_bank_txs,
            settlements=saved_settlements,
            batch_id=batch_id,
        )
        t_elapsed = time.perf_counter() - t_start

        mem_current, mem_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = (mem_peak - mem_before) / (1024 * 1024)

        # 4. Fetch audit scorecard metrics
        processing_time = Decimal(str(t_elapsed)).quantize(Decimal("0.0001"))
        scorecard = await recon_repo.get_scorecard_metrics(
            batch_id=batch_id,
            processing_time_seconds=processing_time,
        )
        await session.commit()

        return {
            "batch_size": batch_size,
            "wall_time_sec": float(t_elapsed),
            "rows_per_sec": float(scorecard["rows_per_second"]),
            "peak_memory_mb": round(peak_mb, 2),
            "match_rate_pct": float(scorecard["total_matched_percentage"]),
            "matched_count": scorecard["total_matched_count"],
            "suggested_count": scorecard["total_suggested_count"],
            "conflict_count": scorecard["total_conflict_count"],
            "exception_count": scorecard["total_exception_count"],
            "exception_amount": float(scorecard["total_exception_amount"]),
            "is_fully_accounted": scorecard["is_fully_accounted"],
            "unaccounted_records": scorecard["unaccounted_records"],
        }


async def main():
    print("=" * 90)
    print("RECONGRID AI - HIGH-THROUGHPUT BATCH BENCHMARK SUITE")
    print("=" * 90)
    await init_db()

    batch_sizes = [50, 200, 500, 1000, 5000]
    results = []

    for size in batch_sizes:
        print(f"[*] Benchmarking batch size: {size:5d} records...", end="", flush=True)
        res = await run_single_benchmark(size)
        results.append(res)
        print(f" Done in {res['wall_time_sec']:.4f}s ({res['rows_per_sec']:,.1f} rows/sec | Peak RAM: {res['peak_memory_mb']} MB)")

    print("\n" + "=" * 90)
    print(f"{'Batch Size':<12} | {'Wall Time':<12} | {'Throughput':<16} | {'Peak Memory':<12} | {'Match Rate':<12} | {'Exceptions (INR)':<16} | {'Conservation':<12}")
    print("-" * 90)
    for r in results:
        status_str = "PASSED (0 lost)" if r["is_fully_accounted"] else "FAILED"
        print(
            f"{r['batch_size']:<12d} | "
            f"{r['wall_time_sec']:<10.4f}s | "
            f"{r['rows_per_sec']:>10.1f} rows/s | "
            f"{r['peak_memory_mb']:>8.2f} MB   | "
            f"{r['match_rate_pct']:>8.2f}%   | "
            f"{r['exception_count']} (INR {r['exception_amount']:,.0f}) | "
            f"{status_str:<12}"
        )
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())
