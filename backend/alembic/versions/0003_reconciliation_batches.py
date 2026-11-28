"""Add reconciliation_batches for month-end close sign-off and ledger freeze.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_batches",
        sa.Column("batch_id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("lock_note", sa.Text(), nullable=True),
        sa.Column("closing_totals", sa.JSON(), nullable=True),
        sa.Column("refund_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("reconciliation_batches")
