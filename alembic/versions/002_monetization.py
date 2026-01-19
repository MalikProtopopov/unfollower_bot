"""Add monetization, queue, and referral tables

Revision ID: 002
Revises: 001
Create Date: 2025-01-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create new enum types
    payment_method_enum = postgresql.ENUM(
        "robokassa", "telegram_stars", "manual",
        name="paymentmethodenum",
        create_type=False
    )
    payment_method_enum.create(op.get_bind(), checkfirst=True)

    payment_status_enum = postgresql.ENUM(
        "pending", "completed", "failed", "cancelled",
        name="paymentstatusenum",
        create_type=False
    )
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    # Add new columns to users table
    op.add_column(
        "users",
        sa.Column("checks_balance", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "users",
        sa.Column("referrer_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("referral_code", sa.String(length=50), nullable=True)
    )
    
    # Add foreign key for referrer_id
    op.create_foreign_key(
        "fk_users_referrer_id",
        "users",
        "users",
        ["referrer_id"],
        ["user_id"],
        ondelete="SET NULL"
    )
    
    # Add unique constraint on referral_code
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)

    # Add new columns to checks table for queue
    op.add_column(
        "checks",
        sa.Column("queue_position", sa.Integer(), nullable=True)
    )
    op.add_column(
        "checks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True)
    )
    
    # Create index for queue processing
    op.create_index("ix_checks_queue_position", "checks", ["queue_position"])

    # Create tariffs table
    op.create_table(
        "tariffs",
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("checks_count", sa.Integer(), nullable=False),
        sa.Column("price_rub", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("price_stars", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tariff_id"),
    )

    # Create payments table
    op.create_table(
        "payments",
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("tariff_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="RUB"),
        sa.Column("checks_count", sa.Integer(), nullable=False),
        sa.Column(
            "payment_method",
            postgresql.ENUM(
                "robokassa", "telegram_stars", "manual",
                name="paymentmethodenum",
                create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "completed", "failed", "cancelled",
                name="paymentstatusenum",
                create_type=False
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("robokassa_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("robokassa_payment_url", sa.Text(), nullable=True),
        sa.Column("telegram_payment_charge_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tariff_id"], ["tariffs.tariff_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("payment_id"),
    )

    # Create indexes for payments
    op.create_index("ix_payments_user_id", "payments", ["user_id"])
    op.create_index("ix_payments_status", "payments", ["status"])
    op.create_index("ix_payments_robokassa_invoice_id", "payments", ["robokassa_invoice_id"])

    # Create referrals table
    op.create_table(
        "referrals",
        sa.Column("referral_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("bonus_granted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("referral_id"),
    )

    # Create indexes for referrals
    op.create_index("ix_referrals_referrer_user_id", "referrals", ["referrer_user_id"])
    op.create_index("ix_referrals_referred_user_id", "referrals", ["referred_user_id"], unique=True)

    # Insert default tariffs
    op.execute("""
        INSERT INTO tariffs (tariff_id, name, description, checks_count, price_rub, price_stars, is_active, sort_order)
        VALUES 
            (gen_random_uuid(), '1 проверка', 'Одна проверка аккаунта', 1, 49.00, 50, true, 1),
            (gen_random_uuid(), '5 проверок', 'Пакет из 5 проверок со скидкой', 5, 199.00, 200, true, 2),
            (gen_random_uuid(), '10 проверок', 'Пакет из 10 проверок с максимальной скидкой', 10, 349.00, 350, true, 3)
    """)


def downgrade() -> None:
    # Drop referrals table and indexes
    op.drop_index("ix_referrals_referred_user_id", table_name="referrals")
    op.drop_index("ix_referrals_referrer_user_id", table_name="referrals")
    op.drop_table("referrals")

    # Drop payments table and indexes
    op.drop_index("ix_payments_robokassa_invoice_id", table_name="payments")
    op.drop_index("ix_payments_status", table_name="payments")
    op.drop_index("ix_payments_user_id", table_name="payments")
    op.drop_table("payments")

    # Drop tariffs table
    op.drop_table("tariffs")

    # Drop queue columns from checks
    op.drop_index("ix_checks_queue_position", table_name="checks")
    op.drop_column("checks", "started_at")
    op.drop_column("checks", "queue_position")

    # Drop new columns from users
    op.drop_index("ix_users_referral_code", table_name="users")
    op.drop_constraint("fk_users_referrer_id", "users", type_="foreignkey")
    op.drop_column("users", "referral_code")
    op.drop_column("users", "referrer_id")
    op.drop_column("users", "checks_balance")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS paymentstatusenum")
    op.execute("DROP TYPE IF EXISTS paymentmethodenum")

