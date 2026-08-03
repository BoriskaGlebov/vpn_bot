"""add index on paymenttransactions gateway_transaction_id

Индекс на PaymentTransaction.gateway_transaction_id — единственный
естественный ключ идемпотентности входящего webhook-события платёжного
провайдера (см. PaymentService.get_by_gateway_id). Без него поиск делает
full scan по мере роста таблицы. Не unique: поле nullable и до момента
привязки провайдера (attach_provider_payment) может быть NULL у нескольких
транзакций одновременно — уникальность контролируется на уровне приложения.

Revision ID: f5bf5fd690ef
Revises: ce828b691be0
Create Date: 2026-08-02 21:26:36.118381

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5bf5fd690ef"
down_revision: Union[str, Sequence[str], None] = "ce828b691be0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_paymenttransactions_gateway_transaction_id"),
        "paymenttransactions",
        ["gateway_transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_paymenttransactions_gateway_transaction_id"),
        table_name="paymenttransactions",
    )
