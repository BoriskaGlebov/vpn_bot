"""make created_at/updated_at and payment paid_at/confirmed_at timezone-aware

created_at/updated_at (Base, все модели) и paymenttransactions.paid_at/
confirmed_at были TIMESTAMP WITHOUT TIME ZONE — наивные значения, при этом
created_at/updated_at ставит Postgres (func.now()), а paid_at/confirmed_at
ставит сам процесс (datetime.now()). Разные часы в одной таблице делают
"paid_at - created_at" бессмысленным при расхождении TZ-настроек контейнеров
(см. issue #255).

Существующие значения приводятся через `AT TIME ZONE 'UTC'`: контейнеры на
проде и в разработке работают в UTC, поэтому наивная метка трактуется как
UTC-время, а не локальное время сессии ALTER TABLE (без явного USING
Postgres использовал бы TimeZone текущей сессии, что совпадает с UTC только
случайно).

Удаление/восстановление индекса ix_paymenttransactions_gateway_transaction_id,
которое добавил автогенератор alembic, сюда не включено — это рассинхрон
схемы, не связанный с задачей таймзон, обсуждать отдельно.

Revision ID: 21a061efdaf6
Revises: 2bd1cafbdb58
Create Date: 2026-10-17 07:15:00.453171

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "21a061efdaf6"
down_revision: Union[str, Sequence[str], None] = "2bd1cafbdb58"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES_WITH_CREATED_UPDATED = [
    "paymenttransactions",
    "referrals",
    "roles",
    "subscriptions",
    "users",
    "vpnconfigs",
]
_PAYMENT_COLUMNS = ["paid_at", "confirmed_at"]


def upgrade() -> None:
    """Upgrade schema."""
    for table in _TABLES_WITH_CREATED_UPDATED:
        for column in ("created_at", "updated_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.TIMESTAMP(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=False,
                existing_server_default=sa.text("now()"),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
    for column in _PAYMENT_COLUMNS:
        op.alter_column(
            "paymenttransactions",
            column,
            existing_type=sa.TIMESTAMP(),
            type_=sa.DateTime(timezone=True),
            existing_nullable=True,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def downgrade() -> None:
    """Downgrade schema."""
    for column in _PAYMENT_COLUMNS:
        op.alter_column(
            "paymenttransactions",
            column,
            existing_type=sa.DateTime(timezone=True),
            type_=sa.TIMESTAMP(),
            existing_nullable=True,
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )
    for table in reversed(_TABLES_WITH_CREATED_UPDATED):
        for column in ("updated_at", "created_at"):
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                type_=sa.TIMESTAMP(),
                existing_nullable=False,
                existing_server_default=sa.text("now()"),
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )
