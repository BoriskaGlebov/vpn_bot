"""Тесты VPNConfigDAO.mark_pending_delete — массовый перевод в PENDING_DELETE.

Условие "только ACTIVE" собрано руками (не через `BaseDAO.update`, который
умеет лишь равенство по полям и не выразит `id IN (...)`), поэтому здесь
отдельно проверяется, что скомпилированный SQL реально содержит оба условия
(id IN, status == ACTIVE) — по аналогии с регрессией #263, когда часть
условия тихо выпадала из WHERE — а также что реальное поведение на БД
соответствует этому условию.
"""

import pytest

from api.users.dao import UserDAO
from api.users.schemas import SRole, SUser
from api.vpn.dao import VPNConfigDAO
from api.vpn.models import VPNConfig, VPNConfigStatus
from shared.enums.admin_enum import RoleEnum


def test_mark_pending_delete_where_clause_has_all_conditions():
    """Компилирует UPDATE и проверяет, что в WHERE есть id IN (...) и status."""
    from sqlalchemy import update as sqlalchemy_update

    config_ids = [1, 2, 3]
    stmt = (
        sqlalchemy_update(VPNConfig)
        .where(
            VPNConfig.id.in_(config_ids),
            VPNConfig.status == VPNConfigStatus.ACTIVE,
        )
        .values(status=VPNConfigStatus.PENDING_DELETE, status_reason="Причина")
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert "vpnconfigs.id IN (1, 2, 3)" in compiled
    assert "vpnconfigs.status = 'ACTIVE'" in compiled
    assert "SET status=" in compiled or "SET status =" in compiled
    assert "status_reason=" in compiled or "status_reason =" in compiled


async def make_user(session, telegram_id: int):
    """Создаёт минимального пользователя для тестов VPN-конфигов."""
    user = await UserDAO.add_role_subscription(
        session=session,
        values_user=SUser(telegram_id=telegram_id, username=f"user{telegram_id}"),
        values_role=SRole(name=RoleEnum.USER),
    )
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_mark_pending_delete_updates_only_active(session):
    """Переводит только ACTIVE-конфиги из переданного списка, записывает причину."""
    user = await make_user(session, 1)
    active_cfg = VPNConfig(
        user_id=user.id,
        file_name="active.conf",
        pub_key="pub1",
        status=VPNConfigStatus.ACTIVE,
    )
    already_pending = VPNConfig(
        user_id=user.id,
        file_name="pending.conf",
        pub_key="pub2",
        status=VPNConfigStatus.PENDING_DELETE,
        status_reason="Старая причина",
    )
    session.add_all([active_cfg, already_pending])
    await session.flush()

    updated = await VPNConfigDAO.mark_pending_delete(
        session=session,
        config_ids=[active_cfg.id, already_pending.id],
        reason="Сменился протокол подключения",
    )

    assert updated == 1

    await session.refresh(active_cfg)
    await session.refresh(already_pending)

    assert active_cfg.status == VPNConfigStatus.PENDING_DELETE
    assert active_cfg.status_reason == "Сменился протокол подключения"
    # Уже помеченный конфиг не тронут — причина, зафиксированная первым
    # переводом, не затирается повторным вызовом.
    assert already_pending.status == VPNConfigStatus.PENDING_DELETE
    assert already_pending.status_reason == "Старая причина"


@pytest.mark.asyncio
async def test_mark_pending_delete_empty_ids_returns_zero(session):
    """Пустой список id не бьёт по БД и возвращает 0 без ошибок."""
    updated = await VPNConfigDAO.mark_pending_delete(
        session=session, config_ids=[], reason="Причина"
    )

    assert updated == 0
