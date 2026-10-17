from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import SubscriptionNotFoundError, VPNLimitError
from api.vpn.dao import VPNConfigDAO, VPNLimitStatus
from api.vpn.models import VPNConfigStatus


@pytest.fixture
def session():
    """Фейковая AsyncSession.

    `spec=AsyncSession` — иначе `AsyncMock()` оборачивает и `session.add`
    (синхронный у `AsyncSession`) в корутину, и невызванный `await`
    настоящего кода даёт `RuntimeWarning: coroutine ... was never awaited`.
    """
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def user():
    sub = MagicMock()
    sub.is_active = True
    sub.type = "pro"

    u = MagicMock()
    u.id = 1
    u.username = "test_user"
    u.current_subscription = sub
    return u


@pytest.mark.asyncio
async def test_get_limit_status_under_limit(session, monkeypatch, user):
    """Текущее число активных конфигов меньше лимита -> can_add=True."""
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {"pro": 2})
    monkeypatch.setattr(VPNConfigDAO, "count", AsyncMock(return_value=0))

    result = await VPNConfigDAO.get_limit_status(session, user)

    assert result == VPNLimitStatus(can_add=True, limit=2, current=0)


@pytest.mark.asyncio
async def test_get_limit_status_over_limit(session, monkeypatch, user):
    """Лимит устройств для типа подписки уже исчерпан -> can_add=False."""
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {"pro": 1})
    monkeypatch.setattr(VPNConfigDAO, "count", AsyncMock(return_value=2))

    result = await VPNConfigDAO.get_limit_status(session, user)

    assert result == VPNLimitStatus(can_add=False, limit=1, current=2)


@pytest.mark.asyncio
async def test_get_limit_status_zero_limit_not_bypassed(session, monkeypatch, user):
    """Регрессия на #269: нулевой лимит не обходится нулевым счётчиком.

    Раньше `count == 0` возвращал `True` до проверки лимита — тип подписки,
    отсутствующий в `DEVICE_LIMITS` (лимит 0), всё равно получал один конфиг.
    """
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {})  # "pro" не описан -> лимит 0
    monkeypatch.setattr(VPNConfigDAO, "count", AsyncMock(return_value=0))

    result = await VPNConfigDAO.get_limit_status(session, user)

    assert result.can_add is False
    assert result.limit == 0


@pytest.mark.asyncio
async def test_get_limit_status_counts_only_active(session, monkeypatch, user):
    """Регрессия на #269: счёт идёт только по статусу ACTIVE.

    `PENDING_DELETE`/`DELETED` не должны занимать слот — проверяется, что
    в `BaseDAO.count` передаётся фильтр именно с `status=VPNConfigStatus.ACTIVE`.
    """
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {"pro": 5})
    count_mock = AsyncMock(return_value=0)
    monkeypatch.setattr(VPNConfigDAO, "count", count_mock)

    await VPNConfigDAO.get_limit_status(session, user)

    filters = count_mock.await_args.kwargs["filters"]
    assert filters.user_id == user.id
    assert filters.status == VPNConfigStatus.ACTIVE


@pytest.mark.asyncio
async def test_get_limit_status_no_subscription_raises(session):
    """Нет активной подписки -> SubscriptionNotFoundError, а не тихий False.

    Регрессия на #269: раньше отсутствие пользователя при вызове из
    `can_add_config` тихо давало `False`, а не единообразное исключение.
    Здесь проверяется вторая половина того же требования — отсутствие
    подписки даёт `SubscriptionNotFoundError` независимо от вызывающего.
    """
    user = MagicMock()
    user.id = 1
    user.username = "test_user"
    user.current_subscription = None

    with pytest.raises(SubscriptionNotFoundError):
        await VPNConfigDAO.get_limit_status(session, user)


@pytest.mark.asyncio
async def test_add_config_raises_limit_with_applied_limit(session, monkeypatch, user):
    """Лимит исчерпан -> add_config() бросает VPNLimitError с применённым лимитом.

    Регрессия на #269: раньше в сообщение об ошибке попадал
    `settings_api.core.max_configs_per_user` (общая настройка), а не лимит,
    который реально применён для типа подписки конкретного пользователя.
    """
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {"pro": 1})
    monkeypatch.setattr(VPNConfigDAO, "count", AsyncMock(return_value=1))

    with pytest.raises(VPNLimitError) as exc:
        await VPNConfigDAO.add_config(
            session=session,
            user=user,
            file_name="test.conf",
            pub_key="key",
        )

    assert exc.value.details["limit"] == 1


@pytest.mark.asyncio
async def test_add_config_creates_when_under_limit(session, monkeypatch, user):
    """Лимит не достигнут -> конфиг создаётся и добавляется в сессию."""
    monkeypatch.setattr("api.vpn.dao.DEVICE_LIMITS", {"pro": 5})
    monkeypatch.setattr(VPNConfigDAO, "count", AsyncMock(return_value=0))

    config = await VPNConfigDAO.add_config(
        session=session,
        user=user,
        file_name="test.conf",
        pub_key="key",
    )

    assert config.user_id == user.id
    assert config.file_name == "test.conf"
    session.add.assert_called_once_with(config)
