"""Razorpay Settlement and Related Financial Entities ORM Models."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from sqlalchemy import Boolean, DateTime, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class RazorpaySettlement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "razorpay_settlements"

    settlement_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)  # Net amount credited
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    fees: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=Decimal("0.00"))
    utr: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="processed", nullable=False)
    settlement_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    is_test_mode: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    reconciliation_logs: Mapped[list["ReconciliationLog"]] = relationship(
        "ReconciliationLog",
        back_populates="rzp_settlement",
        cascade="all, delete-orphan",
    )


class RazorpayRefund(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "razorpay_refunds"

    refund_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    payment_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    settlement_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="processed", nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
