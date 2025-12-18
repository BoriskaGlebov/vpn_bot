from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram.types import User as TgUser

from bot.app_error.base_error import UserNotFoundError, VPNLimitError
from bot.vpn.services import VPNService
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_generate_user_config_success(session, user_service):
    """Проверяем успешную генерацию VPN-конфига."""
    vpn_service = VPNService()

    # Регистрируем тестового пользователя через UserService
    telegram_user = TgUser(
        id=99999,
        username="testuser234",
        first_name="Test",
        last_name="User",
        is_bot=False,
    )
    user_out, created = await user_service.register_or_get_user(session, telegram_user)

    # Мокаем SSH-клиент
    ssh_client = AsyncSSHClientWG(
        host="127.0.0.1",
        username="user",
        known_hosts=None,
        container="test-container",
    )
    ssh_client.add_new_user_gen_config = AsyncMock(
        return_value=(Path("/tmp/test.conf"), "PUB_KEY")
    )

    file_path, pub_key = await vpn_service.generate_user_config(
        session=session, user=telegram_user, ssh_client=ssh_client
    )

    assert file_path == Path("/tmp/test.conf")
    assert pub_key == "PUB_KEY"


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_generate_user_config_user_not_found(session):
    """Проверяем, что генерируемый конфиг для несуществующего пользователя вызывает ошибку."""
    vpn_service = VPNService()
    telegram_user = TgUser(
        id=123456789, username="nouser", first_name="No", last_name="User", is_bot=False
    )
    ssh_client = AsyncSSHClientWG(
        host="127.0.0.1",
        username="user",
        known_hosts=None,
        container="test-container",
    )

    with pytest.raises(UserNotFoundError):
        await vpn_service.generate_user_config(
            session=session, user=telegram_user, ssh_client=ssh_client
        )


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_generate_user_config_limit_reached(session, user_service):
    """Проверяем, что превышение лимита конфигов вызывает VPNLimitError."""
    vpn_service = VPNService()

    telegram_user = TgUser(
        id=88888,
        username="limituser",
        first_name="Limit",
        last_name="User",
        is_bot=False,
    )
    user_out, created = await user_service.register_or_get_user(session, telegram_user)

    # Патчим DAO так, чтобы лимит был превышен
    from bot.vpn.dao import VPNConfigDAO

    VPNConfigDAO.can_add_config = AsyncMock(return_value=False)

    ssh_client = AsyncSSHClientWG(
        host="127.0.0.1",
        username="user",
        known_hosts=None,
        container="test-container",
    )

    with pytest.raises(VPNLimitError):
        await vpn_service.generate_user_config(
            session=session, user=telegram_user, ssh_client=ssh_client
        )


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_get_subscription_info(session, user_service):
    """Проверяем получение информации о подписке."""
    vpn_service = VPNService()
    telegram_user = TgUser(
        id=77777, username="subuser", first_name="Sub", last_name="User", is_bot=False
    )
    user_out, created = await user_service.register_or_get_user(session, telegram_user)

    info_text = await vpn_service.get_subscription_info(
        tg_id=telegram_user.id, session=session
    )
    assert isinstance(info_text, str)
    assert "Активна" in info_text or "Неактивна" in info_text


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_get_subscription_info_user_not_found(session):
    """Проверяем, что для несуществующего пользователя выбрасывается ошибка."""
    vpn_service = VPNService()
    with pytest.raises(UserNotFoundError):
        await vpn_service.get_subscription_info(tg_id=999999999, session=session)
