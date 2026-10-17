from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, F
from aiogram.dispatcher.flags import get_flag
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    FSInputFile,
    InputMediaDocument,
    Message,
    ReplyKeyboardRemove,
    TelegramObject,
)
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.core.config import VPNNode, settings_bot
from bot.core.filters import IsPremium
from bot.integrations.redis_client import RedisClient
from bot.subscription.keyboards.inline_kb import subscription_options_kb
from bot.subscription.router import SubscriptionStates
from bot.subscription.services import SubscriptionService
from bot.users.adapter import UsersAPIAdapter
from bot.users.enums import (
    Location,
    MainMenuText,
    PremiumLocation,
    VPNProtocol,
    available_locations,
    available_premium_locations,
)
from bot.users.utils.text_generator import vpn_button_text
from bot.utils.base_router import BaseRouter
from bot.vpn.keyboards.inline_kb import xray_url_kb
from bot.vpn.keyboards.markup_kb import premium_locations_kb
from bot.vpn.services import SSHClientFactory, VPNService, ssh_client_factory_for

m_vpn = settings_bot.messages.modes.vpn
m_subscription = settings_bot.messages.modes.subscription
x_ray_messages = settings_bot.messages.modes.vpn.x_ray


class LocationFlagMiddleware(BaseMiddleware):
    """Прокидывает флаг `location` хендлера в data по имени параметра.

    Хендлеры регистрируются в цикле по локациям с `flags={"location": loc}`
    (см. `VPNRouter._register_handlers`) — aiogram сохраняет флаг на
    `HandlerObject`, но не инжектирует его в вызов хендлера автоматически.
    Раньше локация повторно выводилась из текста кнопки, который видит
    пользователь (`_get_location_server`), подстрочным поиском — совпадение
    было случайным (например, `'sof' in 'Sofia'`), и переименование ноды
    или локации с похожим названием ломало маршрутизацию молча (см. #268).
    Эта middleware делает уже переданный при регистрации флаг видимым
    хендлеру через параметр `location` — без повторного разбора текста.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Добавляет флаг `location` сработавшего хендлера в `data`, если он есть."""
        location = get_flag(data, "location")
        if location is not None:
            data["location"] = location
        return await handler(event, data)


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
        self.router.message.middleware(LocationFlagMiddleware())

        for location in available_locations():
            self.router.message.register(
                self.get_config_amnezia_wg,
                F.text == vpn_button_text(VPNProtocol.AMNEZIA, location),
                flags={"location": location},
            )
            self.router.message.register(
                self.generate_subscription,
                F.text == vpn_button_text(VPNProtocol.XRAY, location),
                flags={"location": location},
            )
        self.router.message.register(
            self.three_x_ui_locations, F.text == MainMenuText.PREMIUM, is_premium
        )
        self.router.message.register(
            self.upgrade_subscription,
            F.text == MainMenuText.PREMIUM,
        )

        for prem_location in available_premium_locations():
            self.router.message.register(
                self.get_config_amnezia_wg,
                F.text == vpn_button_text(VPNProtocol.AMNEZIA, prem_location),
                is_premium,
                flags={"location": prem_location},
            )
            self.router.message.register(
                self.generate_subscription,
                F.text == vpn_button_text(VPNProtocol.XRAY, prem_location),
                is_premium,
                flags={"location": prem_location},
            )

    async def _check_acquired(self, redis_key: str, message: Message) -> bool:
        """Проверка от повторного создания конфиг файла."""
        acquired = await self.redis.set(redis_key, "1", 60, True)
        if not acquired:
            await message.answer(
                "⏳ Генерация вашего конфига уже в процессе, подождите немного."
            )
            return False
        return True

    async def _handle_vpn_config(
        self,
        *,
        message: Message,
        user: TgUser,
        state: FSMContext,
        ssh_client_factory: SSHClientFactory,
        server_info: VPNNode,
        node_name: str,
        redis_key: str,
        start_text: str,
    ) -> None:
        """Генерирует и отправляет VPN конфигурацию пользователю.

        Args:
            message (Message): входящее сообщение Telegram.
            user (TgUser): пользователь Telegram.
            state (FSMContext): FSM состояние.
            ssh_client_factory (SSHClientFactory): фабрика SSH клиента.
            server_info (VPNNode): конфигурация сервера VPN.
            node_name (str): имя ноды (ключ в settings_bot.vpn.nodes).
            redis_key (str): ключ блокировки генерации.
            start_text (str): текст начала процесса.

        Side Effects
            - создаёт VPN конфиг
            - отправляет файл пользователю
            - очищает FSM и Redis lock

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            status_msg = await message.answer(
                text=start_text,
                reply_markup=ReplyKeyboardRemove(),
            )

            try:
                (
                    file_path1,
                    file_path2,
                    file_path3,
                    pub_key,
                ) = await self.vpn_service.generate_user_config(
                    tg_user=user,
                    ssh_client_factory=ssh_client_factory,
                    server_info=server_info,
                    node_name=node_name,
                )

                try:
                    await status_msg.edit_text(text=m_vpn.config_ready)

                    await message.answer_media_group(
                        media=[
                            InputMediaDocument(media=FSInputFile(file_path1)),
                            InputMediaDocument(media=FSInputFile(file_path2)),
                        ]
                    )
                    # QR — отдельным сообщением: Telegram не даёт мешать
                    # документы и фото в одной media group.
                    await message.answer_photo(
                        photo=FSInputFile(file_path3),
                        caption=m_vpn.qr_caption,
                    )
                finally:
                    # Файлы с приватными ключами не должны оставаться на диске,
                    # даже если отправка пользователю не удалась.
                    file_path1.unlink(missing_ok=True)
                    file_path2.unlink(missing_ok=True)
                    file_path3.unlink(missing_ok=True)

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def get_config_amnezia_wg(
        self,
        message: Message,
        user: TgUser,
        state: FSMContext,
        location: Location | PremiumLocation,
    ) -> None:
        """Генерация конфигурации AmneziaWG.

        Steps:
            1. Определение сервера
            2. Проверка Redis lock
            3. Генерация WG конфигурации
            4. Отправка файла пользователю

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь.
            state (FSMContext): FSM контекст.
            location: Локация, под которую зарегистрирован сработавший
                хендлер (см. `_register_handlers` и `LocationFlagMiddleware`) —
                ключ ноды берётся из неё напрямую, без разбора текста кнопки.

        Returns
            None

        """
        server_info = settings_bot.vpn.get(name=location.value)

        redis_key = f"vpn:config:{user.id}:amnezia_wg"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        await self._handle_vpn_config(
            message=message,
            user=user,
            state=state,
            ssh_client_factory=ssh_client_factory_for(server_info),
            server_info=server_info,
            node_name=location.value,
            redis_key=redis_key,
            start_text=m_vpn.amnezia_wg,
        )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def three_x_ui_locations(self, message: Message, user: TgUser) -> None:
        """Отправляет список доступных XRay-локаций.

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь.

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(
                text=x_ray_messages.intro, reply_markup=premium_locations_kb()
            )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def generate_subscription(
        self,
        message: Message,
        user: TgUser,
        state: FSMContext,
        location: Location | PremiumLocation,
    ) -> None:
        """Генерация XRay подписки для пользователя.

        Flow:
            1. Очистка FSM состояния
            2. Генерация подписки через VPN сервис
            3. Отправка пользователю ссылки и инструкции

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь Telegram.
            state (FSMContext): FSM контекст.
            location: Локация, под которую зарегистрирован сработавший
                хендлер (см. `_register_handlers` и `LocationFlagMiddleware`) —
                ключ ноды берётся из неё напрямую, без разбора текста кнопки.

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()
            xray_location = location.value

            redis_key = f"vpn:config:{user.id}:xray:{xray_location}"
            if not await self._check_acquired(redis_key, message):
                return

            try:
                await message.answer(
                    x_ray_messages.start_generate, reply_markup=ReplyKeyboardRemove()
                )
                url = await self.vpn_service.generate_xray_subscription(
                    tg_user=user, location=xray_location
                )

                await message.answer(
                    text=x_ray_messages.ready_config, reply_markup=xray_url_kb(url=url)
                )
            finally:
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def upgrade_subscription(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Отправляет пользователю сообщение с предложением перейти на премиум-подписку.

        Формирует текст с тарифами и преимуществами премиум-плана, после чего
        отправляет его пользователю вместе с клавиатурой выбора тарифа.

        Перед отправкой переводит FSM в состояние начала оформления подписки.

        Args:
            message (Message): Объект входящего сообщения от пользователя.
            user (TgUser): Объект пользователя Telegram (используется для контекста и логики доступа).
            state (FSMContext): Контекст конечного автомата состояний (FSM) для управления шагами подписки.

        Returns
            None

        Side effects
            - Устанавливает состояние FSM `SubscriptionStates.subscription_start`
            - Отправляет сообщение пользователю с описанием премиум-тарифа
            - Показывает клавиатуру выбора подписки

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.set_state(SubscriptionStates.subscription_start)
            price_map = settings_bot.pricing.price_map_premium
            text = m_subscription.upgrade_subscription.format(
                device_limit=settings_bot.core.max_configs_per_user * 2,
                month=price_map.get(1, 0),
                quarter=price_map.get(3, 0),
                half_year=price_map.get(6, 0),
                year=price_map.get(12, 0),
            )
            await state.update_data(premium=True)
            await message.answer(
                text=text,
                reply_markup=subscription_options_kb(premium=True, trial=False),
            )
