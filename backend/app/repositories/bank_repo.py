"""BankTransaction repository layer."""

from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.bank_transaction import BankTransaction


class BankRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_row_hash(self, row_hash: str) -> BankTransaction | None:
        stmt = select(BankTransaction).where(BankTransaction.row_hash == row_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, tx_id: str) -> BankTransaction | None:
        stmt = select(BankTransaction).where(BankTransaction.id == tx_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_transaction(self, tx_data: dict) -> tuple[BankTransaction, bool]:
        """Upserts a transaction based on row_hash idempotency."""
        existing = await self.get_by_row_hash(tx_data["row_hash"])
        if existing:
            return existing, False

        valid_fields = {
            "batch_id",
            "row_hash",
            "date",
            "amount",
            "direction",
            "utr",
            "description",
            "raw_csv_row",
        }
        filtered_data = {k: v for k, v in tx_data.items() if k in valid_fields}
        new_tx = BankTransaction(**filtered_data)
        self.session.add(new_tx)
        await self.session.flush()
        return new_tx, True

    async def get_all_by_batch(self, batch_id: str = "default") -> Sequence[BankTransaction]:
        stmt = (
            select(BankTransaction)
            .where(BankTransaction.batch_id == batch_id)
            .order_by(BankTransaction.date.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_unreconciled_or_all(self, batch_id: str = "default") -> Sequence[BankTransaction]:
        stmt = (
            select(BankTransaction)
            .where(BankTransaction.batch_id == batch_id)
            .order_by(BankTransaction.date.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
