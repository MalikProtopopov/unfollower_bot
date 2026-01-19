"""Update tariffs with correct Telegram Stars prices

Revision ID: 004
Revises: 003
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Delete old default tariffs and create new ones with correct Stars prices
    # Based on the pricing table from the plan:
    # | Package    | Checks | Stars |
    # |------------|--------|-------|
    # | Small      | 1      | 120   |
    # | Medium     | 3      | 300   |
    # | Large      | 6      | 500   |
    # | Huge       | 14     | 1000  |
    
    # First, deactivate old tariffs (don't delete to preserve payment history)
    op.execute("""
        UPDATE tariffs 
        SET is_active = false
        WHERE is_active = true
    """)
    
    # Insert new tariffs with correct prices
    op.execute("""
        INSERT INTO tariffs (tariff_id, name, description, checks_count, price_rub, price_stars, is_active, sort_order)
        VALUES 
            (gen_random_uuid(), 'Маленький', '1 проверка аккаунта Instagram', 1, 99.00, 120, true, 1),
            (gen_random_uuid(), 'Средний', 'Пакет из 3 проверок со скидкой', 3, 249.00, 300, true, 2),
            (gen_random_uuid(), 'Большой', 'Пакет из 6 проверок с хорошей скидкой', 6, 399.00, 500, true, 3),
            (gen_random_uuid(), 'Огромный', 'Пакет из 14 проверок с максимальной скидкой', 14, 699.00, 1000, true, 4)
    """)


def downgrade() -> None:
    # Delete new tariffs
    op.execute("""
        DELETE FROM tariffs 
        WHERE name IN ('Маленький', 'Средний', 'Большой', 'Огромный')
    """)
    
    # Reactivate old tariffs
    op.execute("""
        UPDATE tariffs 
        SET is_active = true
        WHERE name IN ('1 проверка', '5 проверок', '10 проверок')
    """)

