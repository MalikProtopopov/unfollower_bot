"""Update tariff names and add 1 star tariff

Revision ID: 13c6e0aa524b
Revises: 128748f336e5
Create Date: 2026-01-20 11:37:51.738443

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13c6e0aa524b'
down_revision: Union[str, None] = '128748f336e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Update tariff names to be more descriptive
    op.execute("""
        UPDATE tariffs 
        SET name = '1 проверка', description = '1 проверка аккаунта Instagram'
        WHERE name = 'Маленький' AND checks_count = 1;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = '3 проверки', description = 'Пакет из 3 проверок'
        WHERE name = 'Средний' AND checks_count = 3;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = '6 проверок', description = 'Пакет из 6 проверок'
        WHERE name = 'Большой' AND checks_count = 6;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = '14 проверок', description = 'Пакет из 14 проверок'
        WHERE name = 'Огромный' AND checks_count = 14;
    """)
    
    # Update test tariff names
    op.execute("""
        UPDATE tariffs 
        SET name = '1 проверка (тест)', description = 'Тестовый тариф - 1 звезда за 1 проверку'
        WHERE name = 'Тест: 1 проверка';
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = '3 проверки (тест)', description = 'Тестовый тариф - 2 звезды за 3 проверки'
        WHERE name = 'Тест: 3 проверки';
    """)
    
    # Add new tariff: 1 star for 1 check (main tariff, not test)
    # Check if it doesn't already exist
    op.execute("""
        INSERT INTO tariffs (tariff_id, name, description, checks_count, price_rub, price_stars, is_active, sort_order)
        SELECT 
            gen_random_uuid(), 
            '1 проверка за 1 звезду', 
            '1 проверка аккаунта Instagram за 1 звезду', 
            1, 
            0.00, 
            1, 
            true, 
            0
        WHERE NOT EXISTS (
            SELECT 1 FROM tariffs 
            WHERE checks_count = 1 AND price_stars = 1 AND name != '1 проверка (тест)'
        );
    """)


def downgrade() -> None:
    # Revert tariff names
    op.execute("""
        UPDATE tariffs 
        SET name = 'Маленький', description = '1 проверка аккаунта Instagram'
        WHERE name = '1 проверка' AND checks_count = 1 AND price_stars = 120;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Средний', description = 'Пакет из 3 проверок со скидкой'
        WHERE name = '3 проверки' AND checks_count = 3 AND price_stars = 300;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Большой', description = 'Пакет из 6 проверок с хорошей скидкой'
        WHERE name = '6 проверок' AND checks_count = 6 AND price_stars = 500;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Огромный', description = 'Пакет из 14 проверок с максимальной скидкой'
        WHERE name = '14 проверок' AND checks_count = 14 AND price_stars = 1000;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Тест: 1 проверка', description = 'Тестовый тариф - 1 звезда за 1 проверку'
        WHERE name = '1 проверка (тест)';
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Тест: 3 проверки', description = 'Тестовый тариф - 2 звезды за 3 проверки'
        WHERE name = '3 проверки (тест)';
    """)
    
    # Remove the 1 star tariff
    op.execute("""
        DELETE FROM tariffs 
        WHERE name = '1 проверка за 1 звезду';
    """)

