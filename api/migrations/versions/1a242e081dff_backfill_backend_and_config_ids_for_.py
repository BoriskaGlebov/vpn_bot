"""backfill backend and config_ids for legacy vpnconfig records

Записи VPNConfig, созданные до c3d570092eff (добавившей колонки node_name/
backend/protocol/config_ids), имеют backend=NULL и config_ids=NULL. Код
(bot/vpn/services.py, bot/scheduler/services.py) угадывал бэкенд такой
записи по успешности `json.loads(pub_key)` в четырёх разных местах — для
XRay pub_key хранит JSON-список config_id, для Amnezia — сырой публичный
ключ WireGuard, который как JSON не разбирается (см. issue #270).

Эта миграция заполняет backend/config_ids тем же правилом, что уже
применялось в коде (json.loads + isinstance(..., list) — самая строгая из
четырёх использовавшихся проверок), один раз, здесь. После неё разбор
pub_key в коде не нужен: backend и config_ids можно читать напрямую.

Revision ID: 1a242e081dff
Revises: 21a061efdaf6
Create Date: 2026-10-17 12:19:47.817948

"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a242e081dff"
down_revision: Union[str, Sequence[str], None] = "21a061efdaf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "vpnconfigs"


def upgrade() -> None:
    """Backfill backend/config_ids для записей без backend."""
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(f"SELECT id, pub_key FROM {_TABLE} WHERE backend IS NULL")
    ).fetchall()

    for row_id, pub_key in rows:
        try:
            parsed = json.loads(pub_key)
        except (json.JSONDecodeError, TypeError):
            parsed = None

        if isinstance(parsed, list):
            conn.execute(
                sa.text(
                    f"UPDATE {_TABLE} SET backend = :backend, "
                    "config_ids = :config_ids WHERE id = :id"
                ),
                {
                    "backend": "xray",
                    "config_ids": json.dumps(parsed),
                    "id": row_id,
                },
            )
        else:
            conn.execute(
                sa.text(f"UPDATE {_TABLE} SET backend = :backend WHERE id = :id"),
                {"backend": "amnezia", "id": row_id},
            )


def downgrade() -> None:
    """Намеренно no-op.

    После upgrade новые записи, созданные обычным путём через бота, всегда
    получают backend явно (generate_user_config/generate_xray_subscription
    проставляют его сами) — и для XRay у них pub_key/config_ids совпадают
    по построению точно так же, как у записей, которые заполнила эта
    миграция. Различить "backend поставила миграция" от "backend поставило
    обычное создание конфига" после факта невозможно, поэтому обнуление
    backend/config_ids обратно по любому критерию заодно откатило бы и
    легитимные новые записи. Откатывать здесь нечего: это не схема (колонки
    существовали и были nullable до этой миграции), а данные, которые
    совпадают с тем, что приложение и так считало бы на лету.
    """
