import asyncio
from typing import TYPE_CHECKING

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    FSInputFile,
    InputMediaDocument,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.types import User as TgUser
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.app_error.base_error import AppError, SubscriptionNotFoundError
from bot.core.config import VPNNode, settings_bot
from bot.core.filters import IsPremium
from bot.integrations.redis_client import RedisClient
from bot.subscription.keyboards.inline_kb import subscription_options_kb
from bot.subscription.router import SubscriptionStates
from bot.subscription.services import SubscriptionService
from bot.users.adapter import UsersAPIAdapter
from bot.users.enums import Location, MainMenuText, PremiumLocation, VPNProtocol
from bot.users.utils.text_generator import vpn_button_text
from bot.utils.base_router import BaseRouter
from bot.vpn.keyboards.inline_kb import proxy_url_button, xray_urk_kb
from bot.vpn.keyboards.markup_kb import premium_locations_kb
from bot.vpn.services import SSHClientFactory, VPNService
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG2
from bot.vpn.utils.mtproto import HostDockerSSHClient

if TYPE_CHECKING:
    pass

m_vpn = settings_bot.messages.modes.vpn
m_subscription = settings_bot.messages.modes.subscription
x_ray_messages = settings_bot.messages.modes.vpn.x_ray
# TODO Вернуться на шаг назад к стандартным локациям


class VPNStates(StatesGroup):  # type: ignore[misc]
    """Состояния роутера генерации конфиг файлов."""

    check_location: State = State()


class VPNRouter(BaseRouter):
    """Роутер для обработки команд VPN."""

    main_vpn = settings_bot.vpn.main
    fi_vpn = settings_bot.vpn.fi
    main_proxy = settings_bot.vpn.main.require_proxy()
    fi_proxy = settings_bot.vpn.fi.require_proxy()

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

        for location in Location:
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
            self.upgrade_subscription,
            F.text == MainMenuText.PREMIUM,
        )

        for prem_location in PremiumLocation:
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
        (
            self.router.message.register(
                self.create_proxy_url,
                F.text == MainMenuText.AMNEZIA_PROXY.value,
            ),
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

    async def _get_location_server(
        self,
        message: Message,
    ) -> str | None:
        """Определяет сервер VPN по тексту сообщения.

        Args:
            message (Message): сообщение пользователя с выбранной локацией.

        Returns
            str | None: имя сервера, если найдено совпадение, иначе None.

        Raises
            AppError: если message.text отсутствует.

        """
        if message.text is None:
            raise AppError(
                "Почему-то кнопка не передала текст при выборе локации сервера."
            )
        location = message.text.lower()
        for loc in settings_bot.vpn.nodes:
            is_loc_pref_in = loc in location
            is_location = settings_bot.vpn.get(loc)
            is_flag_in = is_location.flag in location if is_location else False
            if is_loc_pref_in and is_flag_in:
                self.logger.debug(
                    "Определил локацию по тексту кнопки {} -> {}.", location, loc
                )
                return loc
        return None

    async def _handle_vpn_config(
        self,
        *,
        message: Message,
        user: TgUser,
        state: FSMContext,
        ssh_client_factory: SSHClientFactory,
        server_info: VPNNode,
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
                    pub_key,
                ) = await self.vpn_service.generate_user_config(
                    tg_user=user,
                    ssh_client_factory=ssh_client_factory,
                    server_info=server_info,
                )

                await status_msg.answer(text=m_vpn.config_ready)

                await message.answer_media_group(
                    media=[
                        InputMediaDocument(media=FSInputFile(file_path1)),
                        InputMediaDocument(media=FSInputFile(file_path2)),
                    ]
                )

                file_path1.unlink(missing_ok=True)
                file_path2.unlink(missing_ok=True)

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    # @BaseRouter.log_method
    # @BaseRouter.require_user
    # async def get_config_amnezia_vpn(
    #     self,
    #     message: Message,
    #     user: TgUser,
    #     state: FSMContext,
    # ) -> None:
    #     """Генерация конфигурации AmneziaVPN для пользователя.
    #
    #     Flow:
    #         1. Определяет сервер по локации
    #         2. Проверяет блокировку генерации (Redis)
    #         3. Генерирует VPN конфиг
    #         4. Отправляет файл пользователю
    #
    #     Args:
    #         message (Message): входящее сообщение.
    #         user (TgUser): пользователь Telegram.
    #         state (FSMContext): FSM контекст.
    #
    #     Returns
    #         None
    #
    #     """
    #     location = await self._get_location_server(message=message)
    #     if location is None:
    #         raise AppError("Не определил локацию сервера.")
    #     server_info = settings_bot.vpn.get(name=location)
    #
    #     redis_key = f"vpn:config:{user.id}:amnezia_vpn"
    #     acquired_check = await self._check_acquired(redis_key, message)
    #     if not acquired_check:
    #         return
    #
    #     await self._handle_vpn_config(
    #         message=message,
    #         user=user,
    #         state=state,
    #         ssh_client_factory=AsyncSSHClientVPN2,
    #         server_info=server_info,
    #         redis_key=redis_key,
    #         start_text=m_vpn.amnezia_vpn,
    #     )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def get_config_amnezia_wg(
        self, message: Message, user: TgUser, state: FSMContext
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

        Returns
            None

        """
        location = await self._get_location_server(message=message)
        if location is None:
            raise AppError("Не определил локацию сервера.")
        server_info = settings_bot.vpn.get(name=location)

        redis_key = f"vpn:config:{user.id}:amnezia_wg"
        acquired_check = await self._check_acquired(redis_key, message)
        if not acquired_check:
            return
        await self._handle_vpn_config(
            message=message,
            user=user,
            state=state,
            ssh_client_factory=AsyncSSHClientWG2,
            server_info=server_info,
            redis_key=redis_key,
            start_text=m_vpn.amnezia_wg,
        )

    async def _handle_proxy_generation(
        self,
        *,
        message: Message,
        user: TgUser,
        state: FSMContext,
        redis_key: str,
        server_info: VPNNode,
        use_free: bool = False,
    ) -> None:
        """Генерация MTProto proxy URL.

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь Telegram.
            state (FSMContext): FSM контекст.
            redis_key (str): ключ блокировки Redis.
            server_info (VPNNode): конфигурация сервера.
            use_free (bool): использовать ли бесплатный сервер.

        Behavior
            - проверяет подписку (если use_free=False)
            - генерирует proxy URL
            - отправляет пользователю кнопку с ссылкой

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await message.answer(text=m_vpn.proxy_intro)
            await asyncio.sleep(0.5)

            await message.answer(
                text=m_vpn.amnezia_proxy,
                reply_markup=ReplyKeyboardRemove(),
            )

            try:
                if not use_free:
                    info = await self.subscription_service.get_subscription_info(
                        tg_id=user.id
                    )

                    if "Активна" not in info:
                        raise SubscriptionNotFoundError(user_id=user.id)

                url_proxy = await self.vpn_service.get_mtproto_url(
                    ssh_client_factory=HostDockerSSHClient,
                    server_info=server_info,
                )

                keyboard = proxy_url_button(url_proxy=url_proxy)

                if url_proxy:
                    for i, msg in enumerate(m_vpn.proxy_ready):
                        await message.answer(
                            text=msg,
                            reply_markup=keyboard if i == 0 else None,
                        )

            finally:
                await state.clear()
                await self.redis.delete(redis_key)

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def create_proxy_url(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Создание платного MTProto proxy URL.

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь.
            state (FSMContext): FSM контекст.

        Returns
            None

        """
        redis_key = f"vpn:config:{user.id}:amnezia_proxy"

        if not await self._check_acquired(redis_key, message):
            return

        await self._handle_proxy_generation(
            message=message,
            user=user,
            state=state,
            redis_key=redis_key,
            server_info=settings_bot.vpn.main,
            use_free=False,
        )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def create_free_proxy_url(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Создание бесплатного MTProto proxy URL.

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь.
            state (FSMContext): FSM контекст.

        Returns
            None

        """
        redis_key = f"vpn:config:{user.id}:amnezia_proxy"

        if not await self._check_acquired(redis_key, message):
            return

        await self._handle_proxy_generation(
            message=message,
            user=user,
            state=state,
            redis_key=redis_key,
            server_info=settings_bot.vpn.fi,
            use_free=True,
        )

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def three_x_ui_locations(
        self, message: Message, user: TgUser, state: FSMContext
    ) -> None:
        """Отправляет список доступных XRay-локаций и переводит пользователя в FSM состояние выбора.

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь.
            state (FSMContext): FSM контекст.

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
        """Генерация XRay подписки для пользователя.

        Flow:
            1. Очистка FSM состояния
            2. Генерация подписки через VPN сервис
            3. Отправка пользователю ссылки и инструкции

        Args:
            message (Message): входящее сообщение.
            user (TgUser): пользователь Telegram.
            state (FSMContext): FSM контекст.

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()
            xray_location = await self._get_location_server(message=message)
            if xray_location is None:
                raise AppError("Не предалась локация на кнопке вызова Xray конфига")
            await message.answer(
                x_ray_messages.start_generate, reply_markup=ReplyKeyboardRemove()
            )
            url = await self.vpn_service.generate_xray_subscription(
                tg_user=user, location=xray_location
            )

            await message.answer(
                text=x_ray_messages.ready_config, reply_markup=xray_urk_kb(url=url)
            )

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
