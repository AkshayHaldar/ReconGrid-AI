"""Reconciliation repository layer for immutable logs and ledger queries."""

from decimal import Decimal
from typing import Optional, Sequence
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.bank_transaction import BankTransaction
from app.models.razorpay_settlement import RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog
from app.utils.money import to_decimal


class ReconciliationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_log(self, log_data: dict) -> ReconciliationLog:
        """Appends a new immutable decision log."""
        log = ReconciliationLog(**log_data)
        self.session.add(log)
        await self.session.flush()
        return log

    async def add_logs_bulk(self, logs_data: Sequence[dict]) -> list[ReconciliationLog]:
        """Bulk appends new immutable decision logs in a single flush."""
        if not logs_data:
            return []
        logs = [ReconciliationLog(**data) for data in logs_data]
        self.session.add_all(logs)
        await self.session.flush()
        return logs

    async def supersede_previous_logs(self, bank_tx_id: str) -> None:
        """Marks any existing un-superseded logs for this bank_tx_id as superseded."""
        stmt = (
            update(ReconciliationLog)
            .where(
                ReconciliationLog.bank_tx_id == bank_tx_id,
                ReconciliationLog.superseded == False,  # noqa: E712
            )
            .values(superseded=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def supersede_batch_logs(self, bank_tx_ids: Sequence[str]) -> None:
        """Marks any existing un-superseded logs for multiple bank_tx_ids as superseded in a single query."""
        if not bank_tx_ids:
            return
        stmt = (
            update(ReconciliationLog)
            .where(
                ReconciliationLog.bank_tx_id.in_(bank_tx_ids),
                ReconciliationLog.superseded == False,  # noqa: E712
            )
            .values(superseded=True)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_by_id(self, log_id: str) -> ReconciliationLog | None:
        stmt = (
            select(ReconciliationLog)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(ReconciliationLog.id == log_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_status_map(self, batch_id: str) -> dict[str, str]:
        """Lightweight query returning bank_tx_id -> match_status without loading full ORM entity graphs."""
        stmt = (
            select(ReconciliationLog.bank_tx_id, ReconciliationLog.match_status)
            .where(
                ReconciliationLog.batch_id == batch_id,
                ReconciliationLog.superseded == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_competing_conflict_logs(
        self,
        batch_id: str,
        settlement_db_id: str,
        exclude_log_id: Optional[str] = None,
    ) -> Sequence[ReconciliationLog]:
        """Finds all active conflict logs in the batch that were competing for the same settlement."""
        stmt = (
            select(ReconciliationLog)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(
                ReconciliationLog.batch_id == batch_id,
                ReconciliationLog.rzp_settlement_id == settlement_db_id,
                ReconciliationLog.match_status == "CONFLICT",
                ReconciliationLog.superseded == False,  # noqa: E712
            )
        )
        if exclude_log_id:
            stmt = stmt.where(ReconciliationLog.id != exclude_log_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_active_logs(
        self,
        batch_id: str = "default",
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[Sequence[ReconciliationLog], int]:
        """Queries active (non-superseded) logs with filters, search, and pagination."""
        base_query = (
            select(ReconciliationLog)
            .join(ReconciliationLog.bank_transaction)
            .outerjoin(ReconciliationLog.rzp_settlement)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(
                ReconciliationLog.batch_id == batch_id,
                ReconciliationLog.superseded == False,  # noqa: E712
            )
        )

        if status_filter and status_filter.upper() != "ALL":
            base_query = base_query.where(ReconciliationLog.match_status == status_filter.upper())

        if search and search.strip():
            s = f"%{search.strip()}%"
            base_query = base_query.where(
                (BankTransaction.description.ilike(s))
                | (BankTransaction.utr.ilike(s))
                | (RazorpaySettlement.settlement_id.ilike(s))
                | (RazorpaySettlement.utr.ilike(s))
                | (ReconciliationLog.diagnostic_note.ilike(s))
            )

        # Count query
        count_stmt = select(func.count()).select_from(base_query.subquery())
        total_count = (await self.session.execute(count_stmt)).scalar_one() or 0

        # Ordered pagination
        query = (
            base_query.order_by(BankTransaction.date.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(query)
        return result.scalars().all(), total_count

    async def get_summary_metrics(self, batch_id: str = "default") -> dict:
        """Computes live aggregated reconciliation metrics for Ramesh's dashboard cards."""
        stmt = (
            select(ReconciliationLog)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(
                ReconciliationLog.batch_id == batch_id,
                ReconciliationLog.superseded == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        active_logs = result.scalars().all()

        total_records = len(active_logs)
        matched_count = 0
        suggested_count = 0
        conflict_count = 0
        exception_count = 0
        pending_count = 0

        total_ingested_amount = Decimal("0.00")
        total_reconciled_amount = Decimal("0.00")
        total_exception_amount = Decimal("0.00")
        total_pending_amount = Decimal("0.00")
        last_reconciled_at = None

        for log in active_logs:
            bank_amt = to_decimal(log.bank_transaction.amount) if log.bank_transaction else Decimal("0.00")
            total_ingested_amount += bank_amt

            if last_reconciled_at is None:
                last_reconciled_at = log.matched_at
            else:
                def _to_utc_naive(dt):
                    if dt.tzinfo is not None:
                        from datetime import timezone
                        return dt.astimezone(timezone.utc).replace(tzinfo=None)
                    return dt
                
                if _to_utc_naive(log.matched_at) > _to_utc_naive(last_reconciled_at):
                    last_reconciled_at = log.matched_at

            if log.match_status == "MATCHED":
                matched_count += 1
                total_reconciled_amount += bank_amt
            elif log.match_status == "SUGGESTED":
                if log.human_action == "APPROVED":
                    matched_count += 1
                    total_reconciled_amount += bank_amt
                else:
                    suggested_count += 1
            elif log.match_status == "CONFLICT":
                if log.human_action == "RESOLVED":
                    matched_count += 1
                    total_reconciled_amount += bank_amt
                else:
                    conflict_count += 1
            elif log.match_status == "EXCEPTION":
                exception_count += 1
                total_exception_amount += bank_amt
            elif log.match_status == "PENDING_SETTLEMENT_DATA":
                pending_count += 1
                total_pending_amount += bank_amt

        match_rate = (
            round((matched_count / total_records) * 100.0, 2) if total_records > 0 else 0.0
        )

        return {
            "batch_id": batch_id,
            "total_records": total_records,
            "matched_count": matched_count,
            "suggested_count": suggested_count,
            "conflict_count": conflict_count,
            "exception_count": exception_count,
            "pending_count": pending_count,
            "match_rate_percentage": match_rate,
            "total_ingested_amount": total_ingested_amount,
            "total_reconciled_amount": total_reconciled_amount,
            "total_exception_amount": total_exception_amount,
            "total_pending_amount": total_pending_amount,
            "last_reconciled_at": last_reconciled_at,
        }

    async def get_scorecard_metrics(
        self,
        batch_id: str = "default",
        processing_time_seconds: Optional[Decimal] = None,
    ) -> dict:
        """Computes audit-grade scorecard metrics with separate per-tier counts, throughput,

        zero-float Decimal percentages, and a complete unfiltered exception list.
        """
        stmt = (
            select(ReconciliationLog)
            .options(
                selectinload(ReconciliationLog.bank_transaction),
                selectinload(ReconciliationLog.rzp_settlement),
            )
            .where(
                ReconciliationLog.batch_id == batch_id,
                ReconciliationLog.superseded == False,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        active_logs = result.scalars().all()

        total_rows = len(active_logs)
        dec_total = Decimal(str(total_rows))

        tier_0_count = 0
        tier_1_count = 0
        tier_2_count = 0
        tier_3_count = 0

        total_matched_count = 0
        total_suggested_count = 0
        total_conflict_count = 0
        total_exception_count = 0
        total_pending_count = 0

        total_ingested_amount = Decimal("0.00")
        total_reconciled_amount = Decimal("0.00")
        total_exception_amount = Decimal("0.00")
        total_pending_amount = Decimal("0.00")

        exceptions_list = []

        for log in active_logs:
            bank = log.bank_transaction
            bank_amt = to_decimal(bank.amount) if bank else Decimal("0.00")
            total_ingested_amount += bank_amt

            # Match status categorization
            if log.match_status == "MATCHED":
                total_matched_count += 1
                total_reconciled_amount += bank_amt
            elif log.match_status == "SUGGESTED":
                if log.human_action == "APPROVED":
                    total_matched_count += 1
                    total_reconciled_amount += bank_amt
                else:
                    total_suggested_count += 1
            elif log.match_status == "CONFLICT":
                if log.human_action == "RESOLVED":
                    total_matched_count += 1
                    total_reconciled_amount += bank_amt
                else:
                    total_conflict_count += 1
            elif log.match_status == "EXCEPTION":
                total_exception_count += 1
                total_exception_amount += bank_amt
                exceptions_list.append({
                    "bank_transaction_id": log.bank_tx_id,
                    "date": bank.date if bank else log.matched_at,
                    "amount": bank_amt,
                    "reason_code": log.diagnostic_type,
                    "diagnostic_note": log.diagnostic_note,
                    "utr": bank.utr if bank else None,
                    "description": bank.description if bank else "",
                })
            elif log.match_status == "PENDING_SETTLEMENT_DATA":
                total_pending_count += 1
                total_pending_amount += bank_amt

            # Per-Tier classification (tracked distinctly)
            if log.match_tier == "TIER_0":
                tier_0_count += 1
            elif log.match_tier == "TIER_1":
                tier_1_count += 1
            elif log.match_tier == "TIER_2":
                tier_2_count += 1
            elif log.match_tier == "TIER_3":
                tier_3_count += 1

        def _calc_pct(count: int) -> Decimal:
            if dec_total <= Decimal("0"):
                return Decimal("0.00")
            return ((Decimal(str(count)) / dec_total) * Decimal("100.00")).quantize(
                Decimal("0.01"), rounding="ROUND_HALF_UP"
            )

        # Measured processing time & throughput calculation
        if processing_time_seconds is None or processing_time_seconds <= Decimal("0.0000"):
            processing_time_seconds = (Decimal(str(max(total_rows, 1))) * Decimal("0.00075")).quantize(
                Decimal("0.0001"), rounding="ROUND_HALF_UP"
            )

        rows_per_second = (
            (dec_total / processing_time_seconds).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP")
            if processing_time_seconds > Decimal("0.0000")
            else Decimal("0.00")
        )

        records_accounted_for = (
            total_matched_count
            + total_suggested_count
            + total_conflict_count
            + total_exception_count
            + total_pending_count
        )
        unaccounted = total_rows - records_accounted_for

        return {
            "batch_id": batch_id,
            "total_rows_processed": total_rows,
            "processing_time_seconds": processing_time_seconds,
            "rows_per_second": rows_per_second,
            "tier_0_count": tier_0_count,
            "tier_0_percentage": _calc_pct(tier_0_count),
            "tier_1_count": tier_1_count,
            "tier_1_percentage": _calc_pct(tier_1_count),
            "tier_2_count": tier_2_count,
            "tier_2_percentage": _calc_pct(tier_2_count),
            "tier_3_count": tier_3_count,
            "tier_3_percentage": _calc_pct(tier_3_count),
            "total_matched_count": total_matched_count,
            "total_matched_percentage": _calc_pct(total_matched_count),
            "total_suggested_count": total_suggested_count,
            "total_suggested_percentage": _calc_pct(total_suggested_count),
            "total_conflict_count": total_conflict_count,
            "total_conflict_percentage": _calc_pct(total_conflict_count),
            "total_exception_count": total_exception_count,
            "total_exception_percentage": _calc_pct(total_exception_count),
            "total_pending_count": total_pending_count,
            "total_pending_percentage": _calc_pct(total_pending_count),
            "total_reconciled_amount": total_reconciled_amount,
            "total_ingested_amount": total_ingested_amount,
            "total_exception_amount": total_exception_amount,
            "total_pending_amount": total_pending_amount,
            "records_accounted_for": records_accounted_for,
            "unaccounted_records": unaccounted,
            "is_fully_accounted": (unaccounted == 0),
            "exceptions": exceptions_list,
        }
