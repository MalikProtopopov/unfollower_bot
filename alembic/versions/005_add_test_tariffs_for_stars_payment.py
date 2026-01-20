"""Add test tariffs for Stars payment

Revision ID: 005
Revises: 004
Create Date: 2026-01-20 11:20:29.311877

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add test tariffs for Stars payment testing
    # 1. 1 star for 1 check (test tariff)
    # 2. 2 stars for 3 checks (test tariff)
    op.execute("""
        INSERT INTO tariffs (tariff_id, name, description, checks_count, price_rub, price_stars, is_active, sort_order)
        VALUES 
            (gen_random_uuid(), 'Тест: 1 проверка', 'Тестовый тариф - 1 звезда за 1 проверку', 1, 0.00, 1, true, 0),
            (gen_random_uuid(), 'Тест: 3 проверки', 'Тестовый тариф - 2 звезды за 3 проверки', 3, 0.00, 2, true, 0)
    """)


def downgrade() -> None:
    # Remove test tariffs
    op.execute("""
        DELETE FROM tariffs 
        WHERE name IN ('Тест: 1 проверка', 'Тест: 3 проверки')
    """)

