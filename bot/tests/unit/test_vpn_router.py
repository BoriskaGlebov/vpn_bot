from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.types import Chat, Message, ReplyKeyboardRemove, User

from bot.vpn.router import VPNRouter
from bot.vpn.services import VPNService


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_get_config_amnezia_vpn(
    fake_bot, fake_logger, fake_redis, fake_state, session, make_fake_message
):
    # Создаём роутер с мокнутым VPNService
    vpn_service = AsyncMock(spec=VPNService)
    router = VPNRouter(
        bot=fake_bot, logger=fake_logger, vpn_service=vpn_service, redis=fake_redis
    )

    # Мокаем возвращаемые значения generate_user_config
    fake_file = Path("/tmp/test.conf")
    vpn_service.generate_user_config.return_value = (fake_file, "PUB_KEY")

    fake_message = make_fake_message()

    # Патчим SSH-клиент, чтобы не подключаться реально
    with (
        patch(
            "bot.vpn.router.AsyncSSHClientVPN.__aenter__", new_callable=AsyncMock
        ) as mock_ssh_enter,
        patch(
            "bot.vpn.router.AsyncSSHClientVPN.__aexit__", new_callable=AsyncMock
        ) as mock_ssh_exit,
    ):
        mock_ssh_client = AsyncMock()
        mock_ssh_enter.return_value = mock_ssh_client

        await router.get_config_amnezia_vpn(
            message=fake_message, session=session, state=fake_state
        )

        # Проверяем что бот отправил сообщение о генерации
        fake_message.answer.assert_any_await(
            "⏳ Генерирую твой конфиг AmneziaVPN...\nЭто может занять несколько секунд.",
            reply_markup=ReplyKeyboardRemove(),
        )

        # Проверяем, что VPNService.generate_user_config вызван с нужными аргументами
        vpn_service.generate_user_config.assert_awaited_once_with(
            session=session,
            user=fake_message.from_user,
            ssh_client=mock_ssh_client,
        )

        # Проверяем что отправка документа произошла
        fake_message.answer_document.assert_awaited_once()
        # Проверяем, что файл был удалён
        assert not fake_file.exists()

        # Проверяем очистку состояния
        fake_state.clear.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_get_config_amnezia_wg(
    fake_bot, fake_logger, fake_redis, fake_state, session, make_fake_message
):
    vpn_service = AsyncMock(spec=VPNService)
    router = VPNRouter(
        bot=fake_bot, logger=fake_logger, vpn_service=vpn_service, redis=fake_redis
    )

    fake_file = Path("/tmp/test_wg.conf")
    vpn_service.generate_user_config.return_value = (fake_file, "PUB_KEY_WG")

    fake_message = make_fake_message()

    # Патчим SSH-клиент WG
    with (
        patch(
            "bot.vpn.router.AsyncSSHClientWG.__aenter__", new_callable=AsyncMock
        ) as mock_ssh_enter,
        patch(
            "bot.vpn.router.AsyncSSHClientWG.__aexit__", new_callable=AsyncMock
        ) as mock_ssh_exit,
    ):
        mock_ssh_client = AsyncMock()
        mock_ssh_enter.return_value = mock_ssh_client

        await router.get_config_amnezia_wg(
            message=fake_message, session=session, state=fake_state
        )

        fake_message.answer.assert_any_await(
            "⏳ Генерирую твой конфиг AmneziaWG...\nЭто может занять несколько секунд.",
            reply_markup=ReplyKeyboardRemove(),
        )

        vpn_service.generate_user_config.assert_awaited_once_with(
            session=session,
            user=fake_message.from_user,
            ssh_client=mock_ssh_client,
        )

        fake_message.answer_document.assert_awaited_once()
        fake_state.clear.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.vpn
async def test_check_subscription(
    fake_bot, fake_logger, fake_redis, fake_state, session, make_fake_message
):
    router = VPNRouter(
        bot=fake_bot, logger=fake_logger, vpn_service=AsyncMock(), redis=fake_redis
    )
    fake_message = make_fake_message()

    # Патчим метод VPNService.get_subscription_info
    with patch(
        "bot.vpn.router.VPNService.get_subscription_info", new_callable=AsyncMock
    ) as mock_get_info:
        mock_get_info.return_value = "Подписка активна"

        await router.check_subscription(
            message=fake_message, session=session, state=fake_state
        )

        mock_get_info.assert_awaited_once_with(
            tg_id=fake_message.from_user.id, session=session
        )
        fake_message.answer.assert_awaited_with(
            "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
        )
        fake_bot.send_message.assert_awaited_with(
            chat_id=fake_message.from_user.id, text="Подписка активна"
        )
        fake_state.clear.assert_awaited()
