"""Бэкфилл node_name/backend/protocol/config_ids у старых VPNConfig.

Разбирает поля, которые появились в шаге 3 редизайна VPN-моделей
(см. api/vpn/models.py), из уже существующих file_name/pub_key — для
записей, созданных до того, как эти поля начали заполняться на этапе
создания конфига. Источник истины для сопоставления location_prefix -> имя
ноды — тот же `settings_bot.vpn.nodes`, которым пользуется сам бот.

По умолчанию — dry-run (только печатает, что было бы изменено). Реальная
запись в БД — только с флагом --apply.

Запускать как модуль (из корня репозитория) — иначе `api`/`bot`/`shared`
не попадут в sys.path:
    poetry run python -m scripts.backfill_vpn_config_fields            # dry-run
    poetry run python -m scripts.backfill_vpn_config_fields --apply    # применить
"""

import argparse
import asyncio
import json
import re

from sqlalchemy import select

from api.core.database import async_session

# Модели, помимо VPNConfig, напрямую не используются, но их нужно
# импортировать до первого запроса — relationship("User") на VPNConfig
# разрешается SQLAlchemy по имени класса через общий registry, а он
# заполняется только импортом модуля (как в api/migrations/env.py).
from api.users.models import User  # noqa: F401
from api.vpn.models import VPNConfig
from bot.core.config import settings_bot

# У XRay subId префикс однозначно отделён от остального суффиксом "user_" —
# для него обычный regex безопасен.
XRAY_SUBID_RE = re.compile(r"^([A-Za-z]+)user_\d+")


def build_prefix_to_node() -> dict[str, str]:
    """Строит соответствие location_prefix -> имя ноды из конфига бота.

    Returns
        dict[str, str]: Ключ — location_prefix в верхнем регистре
            (например, "DE", "SOF"), значение — имя ноды ("main", "sof").

    """
    return {
        node.location_prefix.upper(): name
        for name, node in settings_bot.vpn.nodes.items()
    }


def _find_node_by_prefix(value: str, prefix_to_node: dict[str, str]) -> str | None:
    """Ищет самый длинный известный location_prefix, с которого начинается value.

    Используется вместо "жадного" regex для Amnezia-имён файлов: после
    префикса локации сразу идёт случайный хвост из букв и цифр без
    разделителя (например, `WGDEc52645.conf`), поэтому regex вида
    `WG([A-Za-z]+)` неизбежно захватывает лишние буквы хвоста (`DEc`).
    Сверка по реальному списку префиксов из `settings_bot.vpn.nodes` снимает
    эту неоднозначность. Сортировка по убыванию длины — на случай, если один
    префикс окажется началом другого (например "SO" и "SOF").

    Args:
        value: Имя файла Amnezia-конфига (`VPNConfig.file_name`), начинается
            с `"WG"`.
        prefix_to_node: Соответствие location_prefix -> имя ноды.

    Returns
        str | None: Имя ноды, если префикс найден, иначе None.

    """
    for prefix in sorted(prefix_to_node, key=len, reverse=True):
        if value.upper().startswith(f"WG{prefix}"):
            return prefix_to_node[prefix]
    return None


def infer_fields(
    config: VPNConfig, prefix_to_node: dict[str, str]
) -> dict[str, object] | None:
    """Определяет node_name/backend/protocol/config_ids для одной строки.

    Бэкенд определяется так же, как везде в остальном коде (см.
    `bot.vpn.services._group_xray_config_ids`): `pub_key`, распарсенный как
    JSON-список, — это XRay; иначе — сырой WG-ключ (Amnezia).

    Args:
        config: Строка VPNConfig с ещё не заполненным node_name.
        prefix_to_node: Соответствие location_prefix -> имя ноды.

    Returns
        dict[str, object] | None: Поля для обновления, либо None — если
            распознать локацию/протокол не удалось (нужен ручной разбор).

    """
    try:
        parsed = json.loads(config.pub_key)
        is_xray = isinstance(parsed, list)
    except json.JSONDecodeError:
        is_xray = False

    if is_xray:
        match = XRAY_SUBID_RE.match(config.file_name)
        if not match:
            return None
        node_name = prefix_to_node.get(match.group(1).upper())
        if node_name is None:
            return None
        return {
            "node_name": node_name,
            "backend": "xray",
            # Какие именно inbound (xhttp/tcp reality) входили в эту
            # подписку, из старых данных не восстановить — только config_ids.
            "protocol": None,
            "config_ids": parsed,
        }

    node_name = _find_node_by_prefix(config.file_name, prefix_to_node)
    if node_name is None:
        return None
    node = settings_bot.vpn.nodes[node_name]
    return {
        "node_name": node_name,
        "backend": "amnezia",
        "protocol": f"wg_{node.protocol_version}",
        "config_ids": None,
    }


async def run(apply: bool) -> None:
    """Проходит по всем VPNConfig без node_name и заполняет их.

    Args:
        apply: Если False (по умолчанию) — только печатает изменения,
            ничего не коммитит. Если True — применяет и коммитит.

    """
    prefix_to_node = build_prefix_to_node()
    updated = 0
    skipped: list[VPNConfig] = []

    async with async_session() as session:
        result = await session.execute(
            select(VPNConfig).where(VPNConfig.node_name.is_(None))
        )
        configs = list(result.scalars().all())
        print(f"Найдено {len(configs)} строк без node_name")

        for config in configs:
            fields = infer_fields(config, prefix_to_node)
            if fields is None:
                skipped.append(config)
                continue
            for key, value in fields.items():
                setattr(config, key, value)
            updated += 1
            print(f"  id={config.id} file_name={config.file_name!r} -> {fields}")

        if skipped:
            print("\nНе удалось распознать (нужен ручной разбор):")
            for config in skipped:
                print(
                    f"  id={config.id} file_name={config.file_name!r} pub_key={config.pub_key!r}"
                )

        if apply:
            await session.commit()
            print(f"Применено: обновлено {updated}, пропущено {len(skipped)}")
        else:
            await session.rollback()
            print(
                f"Dry-run: было бы обновлено {updated}, пропущено {len(skipped)} "
                f"(запустите с --apply, чтобы применить)"
            )


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="реально записать изменения в БД (по умолчанию — dry-run)",
    )
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
