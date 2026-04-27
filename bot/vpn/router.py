import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot, F
from aiogram.filters import StateFilter, and_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    FSInputFile,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.app_error.base_error import SubscriptionNotFoundError
from bot.core.config import settings_bot
from bot.core.filters import IsPremium
from bot.integrations.redis_client import RedisClient
from bot.subscription.services import SubscriptionService
from bot.users.adapter import UsersAPIAdapter
from bot.users.enums import MainMenuText
from bot.utils.base_router import BaseRouter
from bot.vpn.enums import PremiumLocations
from bot.vpn.keyboards.inline_kb import proxy_url_button, xray_urk_kb
from bot.vpn.keyboards.markup_kb import premium_locations_kb
from bot.vpn.services import VPNService
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN2
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG2
from bot.vpn.utils.mtproto import HostDockerSSHClient, MTProtoProxy

if TYPE_CHECKING:
    pass

ssh_lock = asyncio.Lock()
xray_lock = asyncio.Lock()

m_vpn = settings_bot.messages.modes.vpn
m_subscription = settings_bot.messages.modes.subscription
x_ray_messages = settings_bot.messages.modes.vpn.x_ray
premium_locations = [location.value for location in PremiumLocations]


class VPNStates(StatesGroup):  # type: ignore[misc]
    """Состояния роутера генерации конфиг файлов."""

    check_location: State = State()


class VPNRouter(BaseRouter):
    """Роутер для обработки команд VPN."""

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        vpn_service: VPNService,
        redis: RedisClient,
        subscription_service: SubscriptionService,
        user_adapter: UsersAPIAdapter,
    ) -> None:
        self.vpn_service = vpn_service
        self.redis = redis
        self.subscription_service = subscription_service
        self.user_adapter = user_adapter
        super().__init__(bot, logger)

    def _register_handlers(self) -> None:
        """Регистрация хендлеров."""
        is_premium = IsPremium(user_adapter=self.user_adapter)
        self.router.message.register(
            self.get_config_amnezia_vpn,
            F.text == MainMenuText.AMNEZIA_VPN.value,
        )
        self.router.message.register(
            self.get_config_amnezia_wg,
            F.text == MainMenuText.AMNEZIA_WG.value,
        )
        (
            self.router.message.register(
                self.create_proxy_url,
                F.text == MainMenuText.AMNEZIA_PROXY.value,
            ),
        )
        self.router.message.register(
            self.create_free_proxy_url,
            F.text == MainMenuText.FREE_AMNEZIA_PROXY.value,
        )
        self.router.message.register(
            self.three_x_ui_locations, F.text == MainMenuText.PREMIUM, is_premium
        )
        self.router.message.register(
            self.generate_subscription,
            and_f(F.text.in_(premium_locations), StateFilter(VPNStates.check_location)),
            is_premium,
        )

    async def _check_acquired(self, redis_key: str, message: Message) -> bool:
        """Проверка от повторного создания конфиг файла."""
        acquired = await self.redis.set(redis_key, "1", 60, True)
        if not acquired:
            # Уже обрабатывается или уже обработано
            await message.answer(
                "⏳ Генерация вашего конфига уже в процессе, подождите немного."
            )
            return False
        return True

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def get_config_amnezia_vpn(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaVPN."""
        redis_key = f"vpn:config:{user.id}:amnezia_vpn"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                text=m_vpn.amnezia_vpn,
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with AsyncSSHClientVPN2(
                        host=settings_bot.vpn_host,
                        username=settings_bot.vpn_username,
                        known_hosts=None,
                        container=settings_bot.vpn_container,
                    ) as ssh_client:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            tg_user=user,
                            ssh_client=ssh_client,
                        )
                        await status_msg.answer(text=m_vpn.config_ready)

                        await message.answer_document(
                            document=FSInputFile(path=file_path)
                        )
                        file_path.unlink(missing_ok=True)
            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def get_config_amnezia_wg(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Пользователь получает конфиг AmneziaWG."""
        redis_key = f"vpn:config:{user.id}:amnezia_wg"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                text=m_vpn.amnezia_wg,
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with AsyncSSHClientWG2(
                        host=settings_bot.vpn_host,
                        username=settings_bot.vpn_username,
                        known_hosts=None,
                        container=settings_bot.vpn_container,
                    ) as ssh_client:
                        (
                            file_path,
                            pub_key,
                        ) = await self.vpn_service.generate_user_config(
                            tg_user=user,
                            ssh_client=ssh_client,
                        )
                        await status_msg.answer(text=m_vpn.config_ready)

                        await message.answer_document(
                            document=FSInputFile(path=file_path)
                        )
                        file_path.unlink(missing_ok=True)

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def create_proxy_url(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Генерирует уникальный прокси для пользователя и отправляет ссылку в Telegram.

        Args:
            message (Message): Объект сообщения из Telegram.
            user (TgUser): Пользователь Telegram.
            state (FSMContext): Контекст конечного автомата состояния (FSM).

        Raises
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.
            AmneziaSSHError: При ошибках подключения к контейнеру или выполнении команд.
            ValueError: Если данные пользователя некорректны.

        """
        redis_key = f"vpn:config:{user.id}:amnezia_proxy"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(
                text=m_vpn.proxy_intro,
            )
            await asyncio.sleep(0.5)
            await message.answer(
                text=m_vpn.amnezia_proxy,
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with HostDockerSSHClient(
                        host=f"{settings_bot.proxy_prefix}.{settings_bot.vpn_host}",
                        username=settings_bot.vpn_username,
                        use_local=settings_bot.use_local,
                    ) as client:
                        info = await self.subscription_service.get_subscription_info(
                            tg_id=user.id
                        )
                        if "Активна" in info:
                            mtproto = MTProtoProxy(
                                client=client, port=settings_bot.proxy_port
                            )
                            url_proxy = await mtproto.get_proxy_link()
                            keyboard = proxy_url_button(url_proxy=url_proxy)
                            if url_proxy:
                                for num, mess in enumerate(m_vpn.proxy_ready):
                                    if not num:
                                        await message.answer(
                                            text=mess,
                                            reply_markup=keyboard,
                                        )
                                        continue

                                    await message.answer(text=mess)
                        else:
                            raise SubscriptionNotFoundError(user_id=user.id)
            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def create_free_proxy_url(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Генерирует уникальный тестовый  прокси для пользователя и отправляет ссылку в Telegram.

        Args:
            message (Message): Объект сообщения из Telegram.
            user (TgUser): Пользователь Telegram.
            state (FSMContext): Контекст конечного автомата состояния (FSM).

        Raises
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.
            AmneziaSSHError: При ошибках подключения к контейнеру или выполнении команд.
            ValueError: Если данные пользователя некорректны.

        """
        redis_key = f"vpn:config:{user.id}:amnezia_proxy"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(
                text=m_vpn.proxy_intro,
            )
            await asyncio.sleep(0.5)
            await message.answer(
                text=m_vpn.amnezia_proxy,
                reply_markup=ReplyKeyboardRemove(),
            )
            try:
                async with ssh_lock:
                    async with HostDockerSSHClient(
                        host=f"{settings_bot.proxy_test_prefix}.{settings_bot.vpn_test_host}",
                        username=settings_bot.vpn_test_username,
                        use_local=(
                            settings_bot.use_local
                            if settings_bot.vpn_test_host == settings_bot.vpn_host
                            else False
                        ),
                    ) as client:
                        mtproto = MTProtoProxy(
                            client=client, port=settings_bot.proxy_port
                        )
                        url_proxy = await mtproto.get_proxy_link()
                        keyboard = proxy_url_button(url_proxy=url_proxy)
                        if url_proxy:
                            for num, mess in enumerate(m_vpn.proxy_ready):
                                if not num:
                                    await message.answer(
                                        text=mess,
                                        reply_markup=keyboard,
                                    )
                                    continue

                                await message.answer(text=mess)

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def three_x_ui_locations(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Отправляет пользователю список доступных XRay-локаций.

        Используется как первый шаг перед генерацией подписки.

        Args:
            message (Message): входящее сообщение Telegram.
            user (TgUser): текущий пользователь.
            state (FSMContext): FSM-контекст пользователя.

        Side Effects:
            - отправляет сообщение с клавиатурой локаций
            - устанавливает состояние FSM: VPNStates.check_location

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(
                text=x_ray_messages.intro, reply_markup=premium_locations_kb()
            )
            await state.set_state(VPNStates.check_location)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def generate_subscription(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Генерирует XRay subscription URL и отправляет пользователю.

        Полный сценарий:
            1. Сбрасывает FSM состояние
            2. Генерирует подписку через VPN сервис
            3. Отправляет пользователю URL и инструкцию

        Args:
            message (Message): входящее сообщение Telegram.
            user (TgUser): текущий пользователь.
            state (FSMContext): FSM-контекст.

        Side Effects:
            - очищает FSM состояние
            - выполняет SSH-заблокированную операцию генерации
            - отправляет пользователю 2 сообщения:
                1. подтверждение
                2. ссылку на подписку

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            async with xray_lock:
                await state.clear()
                await message.answer(
                    x_ray_messages.start_generate, reply_markup=ReplyKeyboardRemove()
                )
                url = await self.vpn_service.generate_xray_subscription(tg_user=user)

                await message.answer(
                    text=x_ray_messages.ready_config, reply_markup=xray_urk_kb(url=url)
                )
