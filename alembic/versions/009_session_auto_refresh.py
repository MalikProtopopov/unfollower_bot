"""Add session auto-refresh tables and fields

Revision ID: 009
Revises: 008
Create Date: 2026-01-21 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new fields to instagram_sessions table
    op.add_column('instagram_sessions', sa.Column('next_refresh_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('instagram_sessions', sa.Column('fail_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('instagram_sessions', sa.Column('last_error', sa.Text(), nullable=True))
    op.add_column('instagram_sessions', sa.Column('refresh_attempts', sa.Integer(), nullable=False, server_default='0'))
    
    # Create refresh_credentials table for storing Instagram login credentials
    op.create_table(
        'refresh_credentials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('password_encrypted', sa.Text(), nullable=False),
        sa.Column('totp_secret', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_success', sa.Boolean(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    
    # Create check_progress table for resume functionality
    op.create_table(
        'check_progress',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('check_id', sa.UUID(), nullable=False),
        sa.Column('followers_cursor', sa.Text(), nullable=True),
        sa.Column('following_cursor', sa.Text(), nullable=True),
        sa.Column('followers_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('following_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('followers_data', sa.JSON(), nullable=True),
        sa.Column('following_data', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='in_progress'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_update_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['check_id'], ['checks.check_id'], ondelete='CASCADE')
    )
    
    # Create indexes for faster lookups
    op.create_index('ix_check_progress_check_id', 'check_progress', ['check_id'])
    op.create_index('ix_check_progress_status', 'check_progress', ['status'])
    op.create_index('ix_instagram_sessions_next_refresh', 'instagram_sessions', ['next_refresh_at'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_instagram_sessions_next_refresh', table_name='instagram_sessions')
    op.drop_index('ix_check_progress_status', table_name='check_progress')
    op.drop_index('ix_check_progress_check_id', table_name='check_progress')
    
    # Drop tables
    op.drop_table('check_progress')
    op.drop_table('refresh_credentials')
    
    # Remove columns from instagram_sessions
    op.drop_column('instagram_sessions', 'refresh_attempts')
    op.drop_column('instagram_sessions', 'last_error')
    op.drop_column('instagram_sessions', 'fail_count')
    op.drop_column('instagram_sessions', 'next_refresh_at')
