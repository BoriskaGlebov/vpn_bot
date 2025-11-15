import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import bot, settings_bot
from bot.database import connection
from bot.utils.base_router import BaseRouter
from bot.vpn.services import VPNService
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG

if TYPE_CHECKING:
    pass

ssh_lock = asyncio.Lock()


class VPNRouter(BaseRouter):
    """Роутер для обработки команд VPN."""

    key_path = Path().home() / ".ssh" / "test_vpn"

    def __init__(self, bot: Bot, logger: Logger, vpn_service: VPNService) -> None:
        super().__init__(bot, logger)
        self.vpn_service = vpn_service

    def _register_handlers(self) -> None:
        """Регистрация хендлеров."""
        self.router.message.register(
            self.get_config_amnezia_vpn,
            F.text.contains("🔑 Получить VPN-конфиг AmneziaVPN"),
        )
        self.router.message.register(
            self.get_config_amnezia_wg,
            F.text.contains("🌐 Получить VPN-конфиг AmneziaWG"),
        )
        self.router.message.register(
            self.check_subscription,
            F.text.contains("📈 Проверить статус подписки"),
        )

    @BaseRouter.log_method
    @connection()
    async def get_config_amnezia_vpn(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaVPN."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                "⏳ Генерирую твой конфиг AmneziaVPN...\nЭто может занять несколько секунд.",
                reply_markup=ReplyKeyboardRemove(),
            )
            async with ssh_lock:
                async with AsyncSSHClientVPN(
                    host=settings_bot.VPN_HOST,
                    username=settings_bot.VPN_USERNAME,
                    key_filename=self.key_path.as_posix(),
                    known_hosts=None,
                    container=settings_bot.VPN_CONTAINER,
                ) as ssh_client:
                    try:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            session=session,
                            user=message.from_user,
                            ssh_client=ssh_client,
                        )
                    except ValueError as e:
                        await status_msg.answer(str(e))
                        return
                    await status_msg.answer("✅ Конфиг готов! Отправляю...")

                    await message.answer_document(document=FSInputFile(path=file_path))
                    file_path.unlink(missing_ok=True)

            await state.clear()

    @BaseRouter.log_method
    @connection()
    async def get_config_amnezia_wg(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaWG."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                "⏳ Генерирую твой конфиг AmneziaWG...\nЭто может занять несколько секунд.",
                reply_markup=ReplyKeyboardRemove(),
            )
            async with ssh_lock:
                async with AsyncSSHClientWG(
                    host=settings_bot.VPN_HOST,
                    username=settings_bot.VPN_USERNAME,
                    key_filename=self.key_path.as_posix(),
                    known_hosts=None,
                    container=settings_bot.VPN_CONTAINER,
                ) as ssh_client:
                    try:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            session=session,
                            user=message.from_user,
                            ssh_client=ssh_client,
                        )
                    except ValueError as e:
                        await status_msg.answer(str(e))
                        return
                    await status_msg.answer("✅ Конфиг готов! Отправляю...")

                    await message.answer_document(document=FSInputFile(path=file_path))
                    file_path.unlink(missing_ok=True)

            await state.clear()

    @BaseRouter.log_method
    @connection()
    async def check_subscription(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        """Проверка статуса подписки пользователя."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            info_text = await VPNService.get_subscription_info(
                tg_id=message.from_user.id, session=session
            )

            await message.answer(
                "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
            )
            await bot.send_message(chat_id=message.from_user.id, text=info_text)
            await state.clear()
