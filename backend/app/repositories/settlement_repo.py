"""RazorpaySettlement repository layer."""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.razorpay_settlement import RazorpaySettlement, RazorpayRefund


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
