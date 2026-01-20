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
    # Update tariff names to English with interesting names
    # Main tariffs
    op.execute("""
        UPDATE tariffs 
        SET name = 'Basic', description = 'Single Instagram account check'
        WHERE name = 'Маленький' AND checks_count = 1 AND price_stars = 120;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Standard', description = 'Popular pack with 3 checks'
        WHERE name = 'Средний' AND checks_count = 3 AND price_stars = 300;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Pro', description = 'Advanced pack with 6 checks'
        WHERE name = 'Большой' AND checks_count = 6 AND price_stars = 500;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Research', description = 'Ultimate research pack with 14 checks'
        WHERE name = 'Огромный' AND checks_count = 14 AND price_stars = 1000;
    """)
    
    # Update test tariff names
    op.execute("""
        UPDATE tariffs 
        SET name = 'Test', description = 'Test tariff - 1 star for 1 check'
        WHERE name = 'Тест: 1 проверка' OR name = '1 проверка (тест)';
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Test Pack', description = 'Test tariff - 2 stars for 3 checks'
        WHERE name = 'Тест: 3 проверки' OR name = '3 проверки (тест)';
    """)
    
    # Add new tariff: 1 star for 1 check (main tariff, not test)
    # Check if it doesn't already exist
    op.execute("""
        INSERT INTO tariffs (tariff_id, name, description, checks_count, price_rub, price_stars, is_active, sort_order)
        SELECT 
            gen_random_uuid(), 
            'Trial', 
            'Try our service - 1 check for 1 star', 
            1, 
            0.00, 
            1, 
            true, 
            0
        WHERE NOT EXISTS (
            SELECT 1 FROM tariffs 
            WHERE checks_count = 1 AND price_stars = 1 AND name NOT IN ('Test', 'Тест: 1 проверка', '1 проверка (тест)')
        );
    """)


def downgrade() -> None:
    # Revert tariff names to Russian
    op.execute("""
        UPDATE tariffs 
        SET name = 'Маленький', description = '1 проверка аккаунта Instagram'
        WHERE name = 'Basic' AND checks_count = 1 AND price_stars = 120;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Средний', description = 'Пакет из 3 проверок со скидкой'
        WHERE name = 'Standard' AND checks_count = 3 AND price_stars = 300;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Большой', description = 'Пакет из 6 проверок с хорошей скидкой'
        WHERE name = 'Pro' AND checks_count = 6 AND price_stars = 500;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Огромный', description = 'Пакет из 14 проверок с максимальной скидкой'
        WHERE name = 'Research' AND checks_count = 14 AND price_stars = 1000;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Тест: 1 проверка', description = 'Тестовый тариф - 1 звезда за 1 проверку'
        WHERE name = 'Test' AND checks_count = 1 AND price_stars = 1;
    """)
    
    op.execute("""
        UPDATE tariffs 
        SET name = 'Тест: 3 проверки', description = 'Тестовый тариф - 2 звезды за 3 проверки'
        WHERE name = 'Test Pack' AND checks_count = 3 AND price_stars = 2;
    """)
    
    # Remove the Trial tariff
    op.execute("""
        DELETE FROM tariffs 
        WHERE name = 'Trial';
    """)

