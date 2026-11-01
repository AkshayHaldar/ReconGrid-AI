"""Initial schema migration for ReconGrid AI PostgreSQL & SQLite database.

Revision ID: 0001
Revises:
Create Date: 2026-11-01
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. bank_transactions table
    op.create_table(
        "bank_transactions",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False, server_default="CREDIT"),
        sa.Column("utr", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("raw_csv_row", sa.JSON(), nullable=False),
    )
    op.create_index("ix_bank_transactions_id", "bank_transactions", ["id"])
    op.create_index("ix_bank_transactions_batch_id", "bank_transactions", ["batch_id"])
    op.create_index("ix_bank_transactions_row_hash", "bank_transactions", ["row_hash"], unique=True)
    op.create_index("ix_bank_transactions_date", "bank_transactions", ["date"])
    op.create_index("ix_bank_transactions_utr", "bank_transactions", ["utr"])

    # 2. razorpay_settlements table
    op.create_table(
        "razorpay_settlements",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("settlement_id", sa.String(length=64), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("gross_amount", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0.00"),
        sa.Column("fees", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0.00"),
        sa.Column("tax", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0.00"),
        sa.Column("utr", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processed"),
        sa.Column("settlement_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("is_test_mode", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_razorpay_settlements_id", "razorpay_settlements", ["id"])
    op.create_index("ix_razorpay_settlements_settlement_id", "razorpay_settlements", ["settlement_id"], unique=True)
    op.create_index("ix_razorpay_settlements_settlement_created_at", "razorpay_settlements", ["settlement_created_at"])
    op.create_index("ix_razorpay_settlements_utr", "razorpay_settlements", ["utr"])

    # 3. razorpay_refunds table
    op.create_table(
        "razorpay_refunds",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refund_id", sa.String(length=64), nullable=False),
        sa.Column("payment_id", sa.String(length=64), nullable=False),
        sa.Column("settlement_id", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="processed"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
    )
    op.create_index("ix_razorpay_refunds_id", "razorpay_refunds", ["id"])
    op.create_index("ix_razorpay_refunds_refund_id", "razorpay_refunds", ["refund_id"], unique=True)
    op.create_index("ix_razorpay_refunds_payment_id", "razorpay_refunds", ["payment_id"])
    op.create_index("ix_razorpay_refunds_settlement_id", "razorpay_refunds", ["settlement_id"])

    # 4. reconciliation_logs table
    op.create_table(
        "reconciliation_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(length=64), nullable=False, server_default="default"),
        sa.Column("bank_tx_id", sa.String(length=36), sa.ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rzp_settlement_id", sa.String(length=36), sa.ForeignKey("razorpay_settlements.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_status", sa.String(length=32), nullable=False),
        sa.Column("match_tier", sa.String(length=32), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("delta_amount", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0.00"),
        sa.Column("diagnostic_type", sa.String(length=32), nullable=False, server_default="UNRESOLVED"),
        sa.Column("diagnostic_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("human_action", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_reconciliation_logs_id", "reconciliation_logs", ["id"])
    op.create_index("ix_reconciliation_logs_batch_id", "reconciliation_logs", ["batch_id"])
    op.create_index("ix_reconciliation_logs_bank_tx_id", "reconciliation_logs", ["bank_tx_id"])
    op.create_index("ix_reconciliation_logs_rzp_settlement_id", "reconciliation_logs", ["rzp_settlement_id"])
    op.create_index("ix_reconciliation_logs_match_status", "reconciliation_logs", ["match_status"])

    # 5. qa_interaction_logs table
    op.create_table(
        "qa_interaction_logs",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reconciliation_log_id", sa.String(length=36), sa.ForeignKey("reconciliation_logs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("raw_llm_output", sa.Text(), nullable=False, server_default=""),
        sa.Column("final_response", sa.Text(), nullable=False),
        sa.Column("guardrail_rejected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_qa_interaction_logs_id", "qa_interaction_logs", ["id"])
    op.create_index("ix_qa_interaction_logs_reconciliation_log_id", "qa_interaction_logs", ["reconciliation_log_id"])

    # 6. processed_webhook_events table
    op.create_table(
        "processed_webhook_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("razorpay_event_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="PROCESSED"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_processed_webhook_events_id", "processed_webhook_events", ["id"])
    op.create_index("ix_processed_webhook_events_razorpay_event_id", "processed_webhook_events", ["razorpay_event_id"], unique=True)


def downgrade() -> None:
    op.drop_table("processed_webhook_events")
    op.drop_table("qa_interaction_logs")
    op.drop_table("reconciliation_logs")
    op.drop_table("razorpay_refunds")
    op.drop_table("razorpay_settlements")
    op.drop_table("bank_transactions")
