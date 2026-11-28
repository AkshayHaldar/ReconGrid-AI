"""Add SHA-256 audit chain columns to reconciliation_logs.

Existing rows are chained per batch, oldest first, so the verify endpoint works on data created before this migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_audit_chain() -> None:
    # Reuses the model's hash functions so the backfilled chain is exactly what the verifier recomputes.
    from app.models.reconciliation_log import AUDITED_FIELDS, compute_entry_hash, compute_link_hash

    logs = sa.table(
        "reconciliation_logs",
        sa.column("id", sa.String),
        sa.column("batch_id", sa.String),
        sa.column("bank_tx_id", sa.String),
        sa.column("rzp_settlement_id", sa.String),
        sa.column("match_status", sa.String),
        sa.column("match_tier", sa.String),
        sa.column("confidence_score", sa.Float),
        sa.column("delta_amount", sa.Numeric(18, 2)),
        sa.column("diagnostic_type", sa.String),
        sa.column("diagnostic_note", sa.Text),
        sa.column("matched_at", sa.DateTime(timezone=True)),
        sa.column("human_action", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("previous_hash", sa.String),
        sa.column("entry_hash", sa.String),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(*[logs.c[name] for name in AUDITED_FIELDS]).order_by(logs.c.batch_id, logs.c.created_at, logs.c.id)
    ).mappings()

    updates = []
    current_batch = None
    previous_link = None
    for row in rows:
        if row["batch_id"] != current_batch:
            current_batch, previous_link = row["batch_id"], None
        values = dict(row)
        updates.append(
            {
                "row_id": row["id"],
                "prev": previous_link,
                "entry": compute_entry_hash(values, previous_link),
            }
        )
        previous_link = compute_link_hash(values, previous_link)

    if updates:
        bind.execute(
            sa.update(logs)
            .where(logs.c.id == sa.bindparam("row_id"))
            .values(previous_hash=sa.bindparam("prev"), entry_hash=sa.bindparam("entry")),
            updates,
        )


def upgrade() -> None:
    # server_default keeps the ADD COLUMN valid on populated tables; SQLite cannot drop it without rebuilding the
    # table (which would cascade through the foreign keys), so it is only dropped on other dialects.
    op.add_column(
        "reconciliation_logs",
        sa.Column("entry_hash", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column("reconciliation_logs", sa.Column("previous_hash", sa.String(length=64), nullable=True))
    _backfill_audit_chain()
    if op.get_bind().dialect.name != "sqlite":
        op.alter_column("reconciliation_logs", "entry_hash", server_default=None)
    op.create_index("ix_reconciliation_logs_batch_created", "reconciliation_logs", ["batch_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reconciliation_logs_batch_created", table_name="reconciliation_logs")
    op.drop_column("reconciliation_logs", "previous_hash")
    op.drop_column("reconciliation_logs", "entry_hash")
