"""make users.username nullable and non-unique

Telegram-username не обязателен, изменяем и переиспользуем — уникальность
принадлежит telegram_id, не username (см. issue #242).

Revision ID: 2bd1cafbdb58
Revises: c3d570092eff
Create Date: 2026-10-11 19:16:54.800026

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2bd1cafbdb58"
down_revision: Union[str, Sequence[str], None] = "c3d570092eff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("users", "username", existing_type=sa.VARCHAR(), nullable=True)
    op.drop_constraint(op.f("users_username_key"), "users", type_="unique")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint(
        op.f("users_username_key"),
        "users",
        ["username"],
        postgresql_nulls_not_distinct=False,
    )
    op.alter_column("users", "username", existing_type=sa.VARCHAR(), nullable=False)
