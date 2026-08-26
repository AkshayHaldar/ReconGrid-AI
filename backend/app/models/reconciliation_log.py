"""Immutable Append-Only ReconciliationLog ORM Model."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class ReconciliationLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reconciliation_logs"

    batch_id: Mapped[str] = mapped_column(String(64), index=True, default="default")
    bank_tx_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bank_transactions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    rzp_settlement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("razorpay_settlements.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # Match classification
    # MATCHED | SUGGESTED | CONFLICT | EXCEPTION
    match_status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # TIER_0 | TIER_1 | TIER_2 | TIER_3 | MANUAL
    match_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Financial delta & diagnostics
    delta_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
        nullable=False,
    )
    # EXACT_MATCH | FEE_DEDUCTION | REFUND_ADJUSTED | FX_ADJUSTED | REVERSAL | UNRESOLVED
    diagnostic_type: Mapped[str] = mapped_column(String(32), default="UNRESOLVED", nullable=False)
    diagnostic_note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    matched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Immutability tracking: true when a newer record supersedes this decision
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    human_action: Mapped[str | None] = mapped_column(String(32), nullable=True)  # APPROVED | DENIED | RESOLVED

    # Relationships
    bank_transaction: Mapped["BankTransaction"] = relationship(
        "BankTransaction",
        back_populates="reconciliation_logs",
    )
    rzp_settlement: Mapped[Optional["RazorpaySettlement"]] = relationship(
        "RazorpaySettlement",
        back_populates="reconciliation_logs",
    )
    qa_interactions: Mapped[list["QaInteractionLog"]] = relationship(
        "QaInteractionLog",
        back_populates="reconciliation_log",
    )
