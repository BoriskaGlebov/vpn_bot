from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command, StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    Message,
    ReplyKeyboardRemove,
)
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.core.config import settings_bot
from bot.help.enums import DeviceEnum
from bot.help.keyboards.inline_kb import (
    ApkAction,
    ApkCB,
    android_download_kb,
    apk_files_kb,
    apk_version_kb,
    device_keyboard,
    inline_developer_keyboard,
)
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.common_device import Device
from bot.help.utils.happ_device import HappDevice
from bot.help.utils.incy_device import IncyDevice
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.split_device import SplitDevice
from bot.help.utils.tv_device import TVDevice
from bot.integrations.redis_client import RedisClient
from bot.users.enums import ChatType, MainMenuText
from bot.utils.base_router import BaseRouter

m_help = settings_bot.messages.modes.help
links = settings_bot.messages.modes.help.links


class HelpStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для команды /help."""

    device_state: State = State()


class HelpRouter(BaseRouter):
    """Роутер для обработки команды /help и выбора устройства."""

    DEVICE_MAP: dict[str, type[Device]] = {
        DeviceEnum.ANDROID: AndroidDevice,
        DeviceEnum.IOS: IphoneDevice,
        DeviceEnum.PC: PCDevice,
        DeviceEnum.TV: TVDevice,
        DeviceEnum.SPLIT: SplitDevice,
        DeviceEnum.HAPP: HappDevice,
        DeviceEnum.INCY: IncyDevice,
    }

    DEVICE_LABELS: dict[str, str] = {
        DeviceEnum.ANDROID: "Android",
        DeviceEnum.IOS: "iOS",
        DeviceEnum.PC: "Windows / Linux",
        DeviceEnum.TV: "Smart TV",
        DeviceEnum.SPLIT: "раздельное туннелирование",
        DeviceEnum.HAPP: "Happ",
        DeviceEnum.INCY: "INCY",
        "developer": "связь с разработчиком",
    }

    def __init__(self, bot: Bot, logger: Logger, redis: RedisClient) -> None:
        super().__init__(bot, logger)
        self.redis = redis

    def _register_handlers(self) -> None:
        self.router.message.register(
            self.help_cmd,
            or_f(Command("help"), F.text == MainMenuText.HELP.value),
            F.chat.type == ChatType.PRIVATE,
        )
        self.router.message.register(
            self.info_cmd,
            or_f(Command("info"), F.text == MainMenuText.INFO.value),
            F.chat.type == ChatType.PRIVATE,
        )
        self.router.callback_query.register(
            self.device_cb,
            F.data.startswith("device_"),
            StateFilter(HelpStates.device_state),
        )
        self.router.callback_query.register(
            self.noop_cb, F.data == "noop", StateFilter(HelpStates.device_state)
        )
        self.router.callback_query.register(
            self.apk_choice_cb, ApkCB.filter(F.action == ApkAction.CHOICE)
        )
        self.router.callback_query.register(
            self.apk_versions_cb, ApkCB.filter(F.action == ApkAction.VERSIONS)
        )
        self.router.callback_query.register(
            self.apk_files_cb, ApkCB.filter(F.action == ApkAction.FILES)
        )
        self.router.message.register(
            self.mistake_handler_user,
            and_f(StateFilter(HelpStates.device_state), ~F.text.startswith("/")),
        )

    @BaseRouter.log_method
    async def help_cmd(self, message: Message, state: FSMContext) -> None:
        """Обрабатывает команду /help и показывает пользователю первый блок помощи.

        Переходит в состояние выбора устройства, после чего
        отправляет пользователю соответствующие инструкции.

        Args:
            message (Message): Объект сообщения Telegram.
            state (FSMContext): Контекст конечного автомата состояний пользователя.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()
            await message.answer(
                text=m_help.welcome, reply_markup=ReplyKeyboardRemove()
            )
            start_block = m_help.start_block
            for mess in start_block:
                if mess == start_block[-1]:
                    await message.answer(mess, reply_markup=device_keyboard())
                else:
                    await message.answer(mess)
        await state.set_state(HelpStates.device_state)

    @BaseRouter.log_method
    async def noop_cb(self, call: CallbackQuery) -> None:
        """Обрабатывает клик по декоративному разделителю в клавиатуре выбора устройства.

        Ничего не делает, кроме подтверждения callback — не должно влиять
        на состояние FSM пользователя (в отличие от `device_cb`).

        Args:
            call (CallbackQuery): Объект callback-запроса от Telegram.

        """
        await call.answer()

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def apk_choice_cb(self, call: CallbackQuery, msg: Message) -> None:
        """Возвращает к выбору способа установки: Google Play или APK.

        Args:
            call (CallbackQuery): Объект callback-запроса от Telegram.
            msg (Message): Сообщение-экран выбора APK.

        """
        await call.answer()
        apk = m_help.instructions.android_apk
        await msg.edit_text(
            text=apk.choose,
            reply_markup=android_download_kb(m_help.instructions.links.android),
        )

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def apk_versions_cb(self, call: CallbackQuery, msg: Message) -> None:
        """Спрашивает версию Android перед выдачей прямых APK-ссылок.

        Сразу показывать все восемь сборок слишком много для рядового
        пользователя, поэтому сначала сужаем список версией ОС.

        Args:
            call (CallbackQuery): Объект callback-запроса от Telegram.
            msg (Message): Сообщение-экран выбора APK.

        """
        await call.answer()
        apk = m_help.instructions.android_apk
        versions = {key: version.title for key, version in apk.versions.items()}
        await msg.edit_text(text=apk.ask_version, reply_markup=apk_version_kb(versions))

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def apk_files_cb(
        self,
        call: CallbackQuery,
        msg: Message,
        callback_data: ApkCB,
    ) -> None:
        """Отдаёт прямые ссылки на APK для выбранной версии Android.

        Args:
            call (CallbackQuery): Объект callback-запроса от Telegram.
            msg (Message): Сообщение-экран выбора APK.
            callback_data (ApkCB): Данные кнопки (ключ версии Android).

        """
        apk = m_help.instructions.android_apk
        version = apk.versions.get(callback_data.version)
        if not version:
            # Кнопка из старого сообщения, версии в конфиге уже нет.
            self.logger.warning(
                f"Запрошена неизвестная версия Android для APK: {callback_data.version}"
            )
            await call.answer(text="Эта версия больше недоступна", show_alert=True)
            return
        await call.answer()
        await msg.edit_text(text=apk.ask_file, reply_markup=apk_files_kb(version.files))

    @BaseRouter.log_method
    @BaseRouter.require_message
    async def device_cb(
        self,
        call: CallbackQuery,
        msg: Message,
        state: FSMContext,
    ) -> None:
        """Обрабатывает выбор устройства пользователем.

        В зависимости от выбора (Android, iOS, PC, TV)
        вызывает соответствующий метод отправки инструкций.
        Очищается FSM

        Args:
            msg (Message): Сообщение для обработки.
            call (CallbackQuery): Объект callback-запроса от Telegram.
            state (FSMContext): Контекст конечного автомата состояний пользователя.

        """
        data = call.data
        if data is None:
            self.logger.error("CallbackQuery received without data")
            return
        call_device = data.replace("device_", "")
        label = self.DEVICE_LABELS.get(call_device, call_device)
        await call.answer(text=f"Ты выбрал {label}", show_alert=False)
        chat_id = msg.chat.id
        redis_key = f"help:device:{chat_id}:{call_device}"
        acquired = await self.redis.set(redis_key, "1", 60, True)
        if not acquired:
            # Уже обрабатывается или уже обработано
            return
        try:
            async with ChatActionSender.typing(bot=self.bot, chat_id=chat_id):
                device_class = self.DEVICE_MAP.get(call_device)
                if device_class:
                    await msg.delete()
                    await device_class.send_message(bot=self.bot, chat_id=chat_id)
                elif "developer" in call_device:
                    await msg.delete()
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text="Для связи напишите @BorisisTheBlade",
                        reply_markup=inline_developer_keyboard(),
                    )
        finally:
            await self.redis.delete(redis_key)
            await state.clear()

    @BaseRouter.log_method
    async def info_cmd(self, message: Message, state: FSMContext) -> None:
        """Обрабатывает команду /info и показывает пользователю соглашения.

        Для платежной системы важна эта информация.

        Args:
            message (Message): Объект сообщения Telegram.
            state (FSMContext): Контекст конечного автомата состояний пользователя.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            await state.clear()
            await message.answer(
                text=m_help.info,
                reply_markup=ReplyKeyboardRemove(),
                disable_web_page_preview=True,
            )
