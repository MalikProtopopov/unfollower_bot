"""Initial migration - create users, checks, non_mutual_users tables

Revision ID: 001
Revises: 
Create Date: 2025-01-19

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    platform_enum = postgresql.ENUM("instagram", "telegram", name="platformenum", create_type=False)
    platform_enum.create(op.get_bind(), checkfirst=True)

    status_enum = postgresql.ENUM(
        "pending", "processing", "completed", "failed", name="checkstatusenum", create_type=False
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    filetype_enum = postgresql.ENUM("csv", "xlsx", name="filetypeenum", create_type=False)
    filetype_enum.create(op.get_bind(), checkfirst=True)

    # Create users table
    op.create_table(
        "users",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=True),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("avatar_file_id", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
        sa.PrimaryKeyConstraint("user_id"),
    )

    # Create checks table
    op.create_table(
        "checks",
        sa.Column("check_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("target_username", sa.String(length=255), nullable=False),
        sa.Column(
            "platform",
            postgresql.ENUM("instagram", "telegram", name="platformenum", create_type=False),
            nullable=False,
            server_default="instagram",
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "processing", "completed", "failed",
                name="checkstatusenum",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_subscriptions", sa.Integer(), nullable=True),
        sa.Column("total_followers", sa.Integer(), nullable=True),
        sa.Column("total_non_mutual", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column(
            "file_type",
            postgresql.ENUM("csv", "xlsx", name="filetypeenum", create_type=False),
            nullable=True,
        ),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("external_check_id", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("cache_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("check_id"),
    )

    # Create non_mutual_users table
    op.create_table(
        "non_mutual_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("check_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_user_id", sa.String(length=255), nullable=True),
        sa.Column("target_username", sa.String(length=255), nullable=False),
        sa.Column("target_full_name", sa.String(length=500), nullable=True),
        sa.Column("target_avatar_url", sa.String(length=1000), nullable=True),
        sa.Column("user_follows_target", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("target_follows_user", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_mutual", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["check_id"], ["checks.check_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index("ix_checks_user_id", "checks", ["user_id"])
    op.create_index("ix_checks_status", "checks", ["status"])
    op.create_index("ix_checks_created_at", "checks", ["created_at"])
    op.create_index("ix_non_mutual_users_check_id", "non_mutual_users", ["check_id"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_non_mutual_users_check_id", table_name="non_mutual_users")
    op.drop_index("ix_checks_created_at", table_name="checks")
    op.drop_index("ix_checks_status", table_name="checks")
    op.drop_index("ix_checks_user_id", table_name="checks")

    # Drop tables
    op.drop_table("non_mutual_users")
    op.drop_table("checks")
    op.drop_table("users")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS filetypeenum")
    op.execute("DROP TYPE IF EXISTS checkstatusenum")
    op.execute("DROP TYPE IF EXISTS platformenum")

