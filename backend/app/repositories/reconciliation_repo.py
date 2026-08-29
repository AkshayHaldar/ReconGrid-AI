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

        total_ingested_amount = Decimal("0.00")
        total_reconciled_amount = Decimal("0.00")
        total_exception_amount = Decimal("0.00")
        last_reconciled_at = None

        for log in active_logs:
            bank_amt = to_decimal(log.bank_transaction.amount) if log.bank_transaction else Decimal("0.00")
            total_ingested_amount += bank_amt

            if last_reconciled_at is None or log.matched_at > last_reconciled_at:
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
            "match_rate_percentage": match_rate,
            "total_ingested_amount": total_ingested_amount,
            "total_reconciled_amount": total_reconciled_amount,
            "total_exception_amount": total_exception_amount,
            "last_reconciled_at": last_reconciled_at,
        }
