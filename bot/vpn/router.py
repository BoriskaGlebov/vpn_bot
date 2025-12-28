import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, Message, ReplyKeyboardRemove
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings_bot
from bot.database import connection
from bot.redis_manager import SettingsRedis
from bot.utils.base_router import BaseRouter
from bot.vpn.services import VPNService
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG

if TYPE_CHECKING:
    pass

ssh_lock = asyncio.Lock()


class VPNRouter(BaseRouter):
    """Роутер для обработки команд VPN."""

    def __init__(
        self, bot: Bot, logger: Logger, vpn_service: VPNService, redis: SettingsRedis
    ) -> None:
        super().__init__(bot, logger)
        self.vpn_service = vpn_service
        self.redis = redis

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

    async def _check_acquired(self, redis_key: str, message: Message) -> bool:
        """Проверка от повторного создания конфиг файла."""
        acquired = await self.redis.set(redis_key, "1", 60, True)  # NX=True, TTL=60s
        if not acquired:
            # Уже обрабатывается или уже обработано
            await message.answer(
                "⏳ Генерация вашего конфига уже в процессе, подождите немного."
            )
            return False
        return True

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_user
    async def get_config_amnezia_vpn(
        self, message: Message, user: TgUser, session: AsyncSession, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaVPN."""
        redis_key = f"vpn:config:{user.id}:amnezia_vpn"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                "⏳ Генерирую твой конфиг AmneziaVPN...\nЭто может занять несколько секунд.",
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with AsyncSSHClientVPN(
                        host=settings_bot.vpn_host,
                        username=settings_bot.vpn_username,
                        known_hosts=None,
                        container=settings_bot.vpn_container,
                    ) as ssh_client:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            session=session,
                            user=user,
                            ssh_client=ssh_client,
                        )
                        await status_msg.answer("✅ Конфиг готов! Отправляю...")

                        await message.answer_document(
                            document=FSInputFile(path=file_path)
                        )
                        file_path.unlink(missing_ok=True)
            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_user
    async def get_config_amnezia_wg(
        self, message: Message, user: TgUser, session: AsyncSession, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaWG."""
        redis_key = f"vpn:config:{user.id}:amnezia_wg"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                "⏳ Генерирую твой конфиг AmneziaWG...\nЭто может занять несколько секунд.",
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with AsyncSSHClientWG(
                        host=settings_bot.vpn_host,
                        username=settings_bot.vpn_username,
                        known_hosts=None,
                        container=settings_bot.vpn_container,
                    ) as ssh_client:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            session=session,
                            user=user,
                            ssh_client=ssh_client,
                        )
                        await status_msg.answer("✅ Конфиг готов! Отправляю...")

                        await message.answer_document(
                            document=FSInputFile(path=file_path)
                        )
                        file_path.unlink(missing_ok=True)

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @connection()
    @BaseRouter.require_user
    async def check_subscription(
        self, message: Message, user: TgUser, session: AsyncSession, state: FSMContext
    ) -> None:
        """Проверка статуса подписки пользователя."""
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            info_text = await VPNService.get_subscription_info(
                tg_id=user.id, session=session
            )

            await message.answer(
                "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
            )
            await self.bot.send_message(chat_id=user.id, text=info_text)
            await state.clear()
