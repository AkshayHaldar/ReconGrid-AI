"""RazorpaySettlement repository layer."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locks import lock_ledger_freeze
from app.core.logging import logger
from app.models.razorpay_settlement import RazorpayRefund, RazorpaySettlement
from app.models.reconciliation_log import ReconciliationBatch, ReconciliationLog


class SettlementRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_settlement_id(self, settlement_id: str) -> RazorpaySettlement | None:
        stmt = select(RazorpaySettlement).where(RazorpaySettlement.settlement_id == settlement_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, db_id: str) -> RazorpaySettlement | None:
        stmt = select(RazorpaySettlement).where(RazorpaySettlement.id == db_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def frozen_settlement_ids():
        """DB ids of settlements that an active row of a signed-off batch points at."""
        return (
            select(ReconciliationLog.rzp_settlement_id)
            .join(ReconciliationBatch, ReconciliationBatch.batch_id == ReconciliationLog.batch_id)
            .where(
                ReconciliationBatch.is_locked.is_(True),
                ReconciliationLog.superseded.is_(False),
                ReconciliationLog.rzp_settlement_id.is_not(None),
            )
        )

    async def upsert_settlement(self, setl_data: dict) -> tuple[RazorpaySettlement, bool | None]:
        """Upserts a settlement based on settlement_id unique constraint.

        The flag is True for an insert, False for an update, and None when the row was left untouched
        because a signed-off batch shows it.
        """
        await lock_ledger_freeze(self.session)
        existing = await self.get_by_settlement_id(setl_data["settlement_id"])
        if existing:
            if await self.session.scalar(
                self.frozen_settlement_ids().where(ReconciliationLog.rzp_settlement_id == existing.id).limit(1)
            ):
                logger.warning("settlement_update_skipped_batch_locked", settlement_id=existing.settlement_id)
                return existing, None
            # Update fields if necessary
            for k, v in setl_data.items():
                setattr(existing, k, v)
            await self.session.flush()
            return existing, False

        new_setl = RazorpaySettlement(**setl_data)
        self.session.add(new_setl)
        await self.session.flush()
        return new_setl, True

    async def get_all(self) -> Sequence[RazorpaySettlement]:
        stmt = select(RazorpaySettlement).order_by(RazorpaySettlement.settlement_created_at.desc())
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_refunds_for_settlement(self, settlement_id: str) -> Sequence[RazorpayRefund]:
        stmt = select(RazorpayRefund).where(RazorpayRefund.settlement_id == settlement_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def oldest_unlinked_processed_refund(self) -> datetime | None:
        return await self.session.scalar(
            select(func.min(RazorpayRefund.processed_at)).where(
                RazorpayRefund.settlement_id.is_(None), RazorpayRefund.status == "processed",
            )
        )

    async def get_processed_refund_totals(self, settlement_ids: set[str]) -> dict[str, Decimal]:
        totals = {}
        ids = list(settlement_ids)
        for start in range(0, len(ids), 500):
            rows = await self.session.execute(
                select(RazorpayRefund.settlement_id, func.sum(RazorpayRefund.amount))
                .where(RazorpayRefund.settlement_id.in_(ids[start:start + 500]), RazorpayRefund.status == "processed")
                .group_by(RazorpayRefund.settlement_id)
            )
            totals.update((settlement_id, total) for settlement_id, total in rows if settlement_id is not None)
        return totals

    async def get_batch_refund_totals(self, batch_id: str) -> dict[str, str]:
        """Processed refund totals, as decimal strings, for the settlements a batch currently shows."""
        ids = await self.session.scalars(
            select(RazorpaySettlement.settlement_id)
            .join(ReconciliationLog, ReconciliationLog.rzp_settlement_id == RazorpaySettlement.id)
            .where(ReconciliationLog.batch_id == batch_id, ReconciliationLog.superseded.is_(False))
            .distinct()
        )
        totals = await self.get_processed_refund_totals(set(ids))
        return {settlement_id: str(amount) for settlement_id, amount in totals.items()}

    async def link_refund(self, refund_id: str, settlement_id: str) -> None:
        await lock_ledger_freeze(self.session)  # a sign-off must not snapshot refunds mid-write
        await self.session.execute(
            update(RazorpayRefund)
            .where(RazorpayRefund.refund_id == refund_id, RazorpayRefund.settlement_id.is_(None))
            .values(settlement_id=settlement_id)
        )

    async def get_active_batches_for_settlement(self, settlement_id: str) -> Sequence[str]:
        batches = await self.session.scalars(
            select(ReconciliationLog.batch_id)
            .join(RazorpaySettlement, ReconciliationLog.rzp_settlement_id == RazorpaySettlement.id)
            .where(RazorpaySettlement.settlement_id == settlement_id, ReconciliationLog.superseded.is_(False))
            .distinct()
        )
        return batches.all()

    async def upsert_refund(self, refund_data: dict) -> RazorpayRefund:
        """Store both API and webhook deliveries under the same provider refund ID."""
        await lock_ledger_freeze(self.session)  # a sign-off must not snapshot refunds mid-write
        insert = postgres_insert if self.session.get_bind().dialect.name == "postgresql" else sqlite_insert
        statement = insert(RazorpayRefund).values(**refund_data)
        incoming = statement.excluded
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[RazorpayRefund.refund_id],
                set_={
                    "amount": incoming.amount,
                    "status": incoming.status,
                    "processed_at": incoming.processed_at,
                    "raw_payload": incoming.raw_payload,
                    "updated_at": func.now(),
                },
                where=(RazorpayRefund.payment_id == incoming.payment_id)
                & or_(
                    RazorpayRefund.status == "pending",
                    RazorpayRefund.status == incoming.status,
                    incoming.status == "processed",
                ),
            )
        )
        refund = await self.session.scalar(
            select(RazorpayRefund)
            .where(RazorpayRefund.refund_id == refund_data["refund_id"])
            .execution_options(populate_existing=True)
        )
        if refund is None or refund.payment_id != refund_data["payment_id"]:
            raise ValueError("Refund conflicts with the stored payment ID")
        return refund
