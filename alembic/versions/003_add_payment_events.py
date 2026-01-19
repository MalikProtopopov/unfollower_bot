"""Add payment_events table for audit logging

Revision ID: 003
Revises: 002
Create Date: 2026-01-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create payment event type enum
    payment_event_type_enum = postgresql.ENUM(
        "created", "pre_checkout", "completed", "failed", "cancelled",
        "retry_scheduled", "retry_executed",
        name="paymenteventtypeenum",
        create_type=False
    )
    payment_event_type_enum.create(op.get_bind(), checkfirst=True)

    # Create payment_events table
    op.create_table(
        "payment_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "event_type",
            postgresql.ENUM(
                "created", "pre_checkout", "completed", "failed", "cancelled",
                "retry_scheduled", "retry_executed",
                name="paymenteventtypeenum",
                create_type=False
            ),
            nullable=False,
        ),
        sa.Column("status_before", sa.String(length=50), nullable=True),
        sa.Column("status_after", sa.String(length=50), nullable=True),
        sa.Column("details", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["payment_id"],
            ["payments.payment_id"],
            ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # Create indexes for payment_events
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])
    op.create_index("ix_payment_events_event_type", "payment_events", ["event_type"])
    op.create_index("ix_payment_events_created_at", "payment_events", ["created_at"])

    # Add index on telegram_payment_charge_id in payments table for idempotency checks
    op.create_index(
        "ix_payments_telegram_payment_charge_id",
        "payments",
        ["telegram_payment_charge_id"],
        unique=False
    )


def downgrade() -> None:
    # Drop index on telegram_payment_charge_id
    op.drop_index("ix_payments_telegram_payment_charge_id", table_name="payments")

    # Drop payment_events table and indexes
    op.drop_index("ix_payment_events_created_at", table_name="payment_events")
    op.drop_index("ix_payment_events_event_type", table_name="payment_events")
    op.drop_index("ix_payment_events_payment_id", table_name="payment_events")
    op.drop_table("payment_events")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS paymenteventtypeenum")

