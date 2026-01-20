"""add instagram_sessions table

Revision ID: 007
Revises: f73d7ff2c911
Create Date: 2026-01-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = 'f73d7ff2c911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create instagram_sessions table
    op.create_table(
        'instagram_sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on is_active for faster lookups
    op.create_index('ix_instagram_sessions_is_active', 'instagram_sessions', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_instagram_sessions_is_active', table_name='instagram_sessions')
    op.drop_table('instagram_sessions')

