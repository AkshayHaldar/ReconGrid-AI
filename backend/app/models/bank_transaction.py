"""BankTransaction ORM Model."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from sqlalchemy import DateTime, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class BankTransaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "bank_transactions"

    batch_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    row_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), default="CREDIT", nullable=False)  # CREDIT | DEBIT
    utr: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_csv_row: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    # Relationships
    reconciliation_logs: Mapped[list["ReconciliationLog"]] = relationship(
        "ReconciliationLog",
        back_populates="bank_transaction",
        cascade="all, delete-orphan",
    )
