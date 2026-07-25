"""preserve payments/referrals on user delete (SET NULL)

Revision ID: ce828b691be0
Revises: 38615af52e74
Create Date: 2026-07-25 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ce828b691be0"
down_revision: Union[str, Sequence[str], None] = "38615af52e74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Платежи и рефералы должны переживать удаление пользователя (для истории/
    бухгалтерии) вместо каскадного удаления/падения на NOT NULL. Меняем
    ondelete с CASCADE на SET NULL и делаем связанные FK-колонки nullable.
    """
    op.drop_constraint(
        "paymenttransactions_user_id_fkey", "paymenttransactions", type_="foreignkey"
    )
    op.alter_column("paymenttransactions", "user_id", nullable=True)
    op.create_foreign_key(
        "paymenttransactions_user_id_fkey",
        "paymenttransactions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("referrals_inviter_id_fkey", "referrals", type_="foreignkey")
    op.alter_column("referrals", "inviter_id", nullable=True)
    op.create_foreign_key(
        "referrals_inviter_id_fkey",
        "referrals",
        "users",
        ["inviter_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.drop_constraint("referrals_invited_id_fkey", "referrals", type_="foreignkey")
    op.alter_column("referrals", "invited_id", nullable=True)
    op.create_foreign_key(
        "referrals_invited_id_fkey",
        "referrals",
        "users",
        ["invited_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("referrals_invited_id_fkey", "referrals", type_="foreignkey")
    op.alter_column("referrals", "invited_id", nullable=False)
    op.create_foreign_key(
        "referrals_invited_id_fkey",
        "referrals",
        "users",
        ["invited_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("referrals_inviter_id_fkey", "referrals", type_="foreignkey")
    op.alter_column("referrals", "inviter_id", nullable=False)
    op.create_foreign_key(
        "referrals_inviter_id_fkey",
        "referrals",
        "users",
        ["inviter_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint(
        "paymenttransactions_user_id_fkey", "paymenttransactions", type_="foreignkey"
    )
    op.alter_column("paymenttransactions", "user_id", nullable=False)
    op.create_foreign_key(
        "paymenttransactions_user_id_fkey",
        "paymenttransactions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
