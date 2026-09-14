"""add node_name backend protocol config_ids to vpnconfig

Revision ID: c3d570092eff
Revises: f5bf5fd690ef
Create Date: 2026-09-14 11:01:18.447989

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d570092eff"
down_revision: Union[str, Sequence[str], None] = "f5bf5fd690ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "vpnconfigs", sa.Column("node_name", sa.String(length=50), nullable=True)
    )
    op.add_column(
        "vpnconfigs", sa.Column("backend", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "vpnconfigs", sa.Column("protocol", sa.String(length=50), nullable=True)
    )
    op.add_column("vpnconfigs", sa.Column("config_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("vpnconfigs", "config_ids")
    op.drop_column("vpnconfigs", "protocol")
    op.drop_column("vpnconfigs", "backend")
    op.drop_column("vpnconfigs", "node_name")
