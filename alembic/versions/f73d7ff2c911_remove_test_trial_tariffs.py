"""remove_test_trial_tariffs

Revision ID: f73d7ff2c911
Revises: 006
Create Date: 2026-01-20 12:55:32.285155

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f73d7ff2c911'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove test and trial tariffs
    # These are temporary tariffs that should not be recreated on restart
    op.execute("""
        DELETE FROM tariffs 
        WHERE name IN ('Test', 'Test Pack', 'Trial', 'Тест: 1 проверка', 'Тест: 3 проверки', '1 проверка (тест)', '3 проверки (тест)');
    """)


def downgrade() -> None:
    # Recreate test tariffs if needed (optional - usually not needed)
    # This is left empty as we don't want to recreate test tariffs
    pass

