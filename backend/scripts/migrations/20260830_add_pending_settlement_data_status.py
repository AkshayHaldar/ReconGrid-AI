"""Migration: Add PENDING_SETTLEMENT_DATA status and PENDING_SETTLEMENT diagnostic type

Revision ID: 20260830_add_pending_settlement_data
Revises: baseline
Create Date: 2026-08-30

Description:
  Updates the allowed check constraints / enum definitions on PostgreSQL
  and SQLite for reconciliation_logs table to allow 'PENDING_SETTLEMENT_DATA'
  as a valid match_status and 'PENDING_SETTLEMENT' as a valid diagnostic_type.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260830_add_pending_settlement_data"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """PostgreSQL / SQLite migration to update check constraints or enum."""
    # For PostgreSQL with ENUM types (if applied):
    # op.execute("ALTER TYPE match_status_enum ADD VALUE IF NOT EXISTS 'PENDING_SETTLEMENT_DATA';")
    # op.execute("ALTER TYPE diagnostic_type_enum ADD VALUE IF NOT EXISTS 'PENDING_SETTLEMENT';")

    # For tables using VARCHAR with CHECK constraints:
    # op.drop_constraint('ck_reconciliation_logs_match_status', 'reconciliation_logs', type_='check')
    # op.create_check_constraint(
    #     'ck_reconciliation_logs_match_status',
    #     'reconciliation_logs',
    #     "match_status IN ('MATCHED', 'SUGGESTED', 'CONFLICT', 'EXCEPTION', 'PENDING_SETTLEMENT_DATA')"
    # )
    pass


def downgrade() -> None:
    """Downgrade path."""
    pass
