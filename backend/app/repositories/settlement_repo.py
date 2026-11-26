"""RazorpaySettlement repository layer."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.razorpay_settlement import RazorpayRefund, RazorpaySettlement
from app.models.reconciliation_log import ReconciliationLog


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

    async def upsert_settlement(self, setl_data: dict) -> tuple[RazorpaySettlement, bool]:
        """Upserts a settlement based on settlement_id unique constraint."""
        existing = await self.get_by_settlement_id(setl_data["settlement_id"])
        if existing:
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

    async def link_refund(self, refund_id: str, settlement_id: str) -> None:
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
