"""Auditable QA Interaction Log ORM Model."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class QaInteractionLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "qa_interaction_logs"

    reconciliation_log_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("reconciliation_logs.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    raw_llm_output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    final_response: Mapped[str] = mapped_column(Text, nullable=False)
    guardrail_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    reconciliation_log: Mapped["ReconciliationLog"] = relationship(
        "ReconciliationLog",
        back_populates="qa_interactions",
    )
