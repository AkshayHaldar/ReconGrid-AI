"""Immutable Append-Only ReconciliationLog ORM Model.

Every row carries a SHA-256 audit chain so out-of-band edits (plain SQL) are detectable:

* ``entry_hash``    seals the whole row: previous_hash + every audited field (see ``AUDITED_FIELDS``).
* ``previous_hash`` is the *link hash* of the preceding row in the same batch (``None`` for the first row).
  A link hash only covers a row's identity (id, batch_id, bank_tx_id, created_at) plus its own previous_hash.

Human decisions (approve / deny / resolve) edit a row in place, so they re-seal that one row's ``entry_hash``
without touching its neighbours, but only when the stored row still matched its seal beforehand: a row that was
edited with plain SQL stays COMPROMISED after a later approve. Deleting, inserting or reordering rows breaks the link hashes instead.
``superseded``, ``superseded_by_id`` and ``updated_at`` are lifecycle bookkeeping and are not audited.
"""

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Numeric, String, Text, event, select, text
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDMixin

AUDIT_HASH_VERSION = 1

# Columns sealed by entry_hash. Anything not listed here may change without breaking the chain.
AUDITED_FIELDS = (
    "id",
    "batch_id",
    "bank_tx_id",
    "rzp_settlement_id",
    "match_status",
    "match_tier",
    "confidence_score",
    "delta_amount",
    "diagnostic_type",
    "diagnostic_note",
    "matched_at",
    "human_action",
    "created_at",
)
# Columns that never change after insert; these (plus previous_hash) form the chain link.
LINK_FIELDS = ("id", "batch_id", "bank_tx_id", "created_at")


def _canon(name: str, value: Any) -> str | None:
    """Stable text form of a column value, identical before insert and after a DB round trip."""
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat(timespec="microseconds")
    if name == "delta_amount":
        return format(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    if name == "confidence_score":
        return repr(float(value))
    return str(value)


def _digest(kind: str, previous_hash: str | None, values: Mapping[str, Any], fields: tuple[str, ...]) -> str:
    payload = {
        "kind": kind,
        "version": AUDIT_HASH_VERSION,
        "previous_hash": previous_hash,
        "fields": {name: _canon(name, values.get(name)) for name in fields},
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def compute_entry_hash(values: Mapping[str, Any], previous_hash: str | None) -> str:
    """SHA-256 over previous_hash and every audited field of one log row."""
    return _digest("entry", previous_hash, values, AUDITED_FIELDS)


def compute_link_hash(values: Mapping[str, Any], previous_hash: str | None) -> str:
    """SHA-256 over a row's immutable identity; the next row stores this as its previous_hash."""
    return _digest("link", previous_hash, values, LINK_FIELDS)


class ReconciliationLog(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "reconciliation_logs"
    __table_args__ = (Index("ix_reconciliation_logs_batch_created", "batch_id", "created_at"),)

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
    # MATCHED | SUGGESTED | CONFLICT | EXCEPTION | PENDING_SETTLEMENT_DATA
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
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    # Immutability tracking: true when a newer record supersedes this decision
    superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    human_action: Mapped[str | None] = mapped_column(String(32), nullable=True)  # APPROVED | DENIED | RESOLVED

    # SHA-256 audit chain (see module docstring)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

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

    def _values(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in AUDITED_FIELDS}

    def compute_entry_hash(self) -> str:
        return compute_entry_hash(self._values(), self.previous_hash)

    def compute_link_hash(self) -> str:
        return compute_link_hash(self._values(), self.previous_hash)

    def seal(self) -> None:
        """Recompute entry_hash from the current field values (previous_hash is left as is)."""
        self.entry_hash = self.compute_entry_hash()


def _apply_insert_defaults(log: ReconciliationLog, now: datetime) -> None:
    """Column defaults only run at INSERT time, but the hash needs the final values before that."""
    if log.id is None:
        log.id = str(uuid.uuid4())
    if log.batch_id is None:
        log.batch_id = "default"
    if log.delta_amount is None:
        log.delta_amount = Decimal("0.00")
    if log.diagnostic_type is None:
        log.diagnostic_type = "UNRESOLVED"
    if log.diagnostic_note is None:
        log.diagnostic_note = ""
    if log.matched_at is None:
        log.matched_at = now
    if log.superseded is None:
        log.superseded = False


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _audited_fields_changed(log: ReconciliationLog) -> bool:
    """True when an audited column has a pending net change (lifecycle columns like superseded do not count)."""
    attrs = sa_inspect(log).attrs
    return any(attrs[name].history.has_changes() for name in AUDITED_FIELDS)


def audit_columns() -> list[Any]:
    """Every column needed to recompute a row's entry_hash, plus the stored seal itself."""
    return [
        *(getattr(ReconciliationLog, name) for name in AUDITED_FIELDS),
        ReconciliationLog.previous_hash,
        ReconciliationLog.entry_hash,
    ]


def row_matches_seal(row: Any) -> bool:
    """True when a row selected with ``audit_columns()`` still hashes to its stored entry_hash."""
    return compute_entry_hash(row._mapping, row.previous_hash) == row.entry_hash


def _ids_with_intact_stored_row(session: Session, ids: list[str]) -> set[str]:
    """Ids whose row, as currently stored in the database, still matches its own entry_hash.

    Reads the stored columns (not the pending ORM values), so a plain-SQL edit made after the row was
    sealed shows up here even if the application is now changing the same row through the ORM.
    """
    connection = session.connection()
    intact: set[str] = set()
    for start in range(0, len(ids), 500):
        stmt = select(*audit_columns()).where(ReconciliationLog.id.in_(ids[start : start + 500]))
        intact.update(row.id for row in connection.execute(stmt) if row_matches_seal(row))
    return intact


@event.listens_for(Session, "before_flush")
def _chain_reconciliation_logs(session: Session, flush_context: Any, instances: Any) -> None:
    """Seal new logs onto their batch's chain and re-seal logs whose audited fields were edited.

    Runs for every writer (engine, approve/deny/resolve handlers, tests), so no log is ever stored unchained.
    """
    edited = [
        o
        for o in session.dirty
        if isinstance(o, ReconciliationLog) and o.entry_hash is not None and _audited_fields_changed(o)
    ]
    if edited:
        intact = _ids_with_intact_stored_row(session, [o.id for o in edited])
        for obj in edited:
            # A row whose stored state no longer matches its seal was edited out of band: leave the old
            # entry_hash in place so verification keeps reporting it instead of blessing the tampered values.
            if obj.id in intact:
                obj.seal()

    new_logs = [o for o in session.new if isinstance(o, ReconciliationLog) and o.entry_hash is None]
    if not new_logs:
        return

    now = datetime.now(UTC)
    by_batch: dict[str, list[ReconciliationLog]] = {}
    for log in new_logs:
        _apply_insert_defaults(log, now)
        by_batch.setdefault(log.batch_id, []).append(log)

    connection = session.connection()
    for batch_id, logs in by_batch.items():
        if connection.dialect.name == "postgresql":
            # Serialise writers per batch until commit so two requests cannot fork the chain.
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:b))"), {"b": f"recon-audit:{batch_id}"})

        tail = connection.execute(
            select(
                ReconciliationLog.id,
                ReconciliationLog.batch_id,
                ReconciliationLog.bank_tx_id,
                ReconciliationLog.created_at,
                ReconciliationLog.previous_hash,
            )
            .where(ReconciliationLog.batch_id == batch_id)
            .order_by(ReconciliationLog.created_at.desc(), ReconciliationLog.id.desc())
            .limit(1)
        ).first()

        previous_link: str | None = None
        last_ts = now - timedelta(microseconds=1)
        if tail is not None:
            previous_link = compute_link_hash(dict(tail._mapping), tail.previous_hash)
            last_ts = max(last_ts, _utc(tail.created_at))

        for log in logs:
            # Strictly increasing created_at gives every batch one unambiguous chain order.
            last_ts = max(now, last_ts + timedelta(microseconds=1))
            log.created_at = last_ts
            log.previous_hash = previous_link
            log.seal()
            previous_link = log.compute_link_hash()


class ReconciliationBatch(Base, TimestampMixin):
    """Per-batch period close state.

    A batch is just a ``batch_id`` string on the log rows, so this table holds the metadata that
    belongs to the batch as a whole. A row only exists once a batch has been signed off.
    Once ``is_locked`` is set the ledger for that batch is read-only (HTTP 423 on writes).
    """

    __tablename__ = "reconciliation_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lock_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Totals frozen at sign-off time (amounts stored as decimal strings, never floats).
    closing_totals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Refund total per settlement_id at sign-off; a locked batch's tax schedule reads these.
    refund_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
