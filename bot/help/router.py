from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command, StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.config import settings_bot
from bot.help.enums import DeviceEnum
from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.common_device import Device
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice
from bot.redis_manager import SettingsRedis
from bot.users.enums import ChatType
from bot.utils.base_router import BaseRouter

m_help = settings_bot.messages.modes.help


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
    }

    def __init__(self, bot: Bot, logger: Logger, redis: SettingsRedis) -> None:
        super().__init__(bot, logger)
        self.redis = redis

    def _register_handlers(self) -> None:
        self.router.message.register(
            self.help_cmd,
            or_f(Command("help"), F.text.contains("❓ Помощь в настройке VPN")),
            F.chat.type == ChatType.PRIVATE,
        )
        self.router.callback_query.register(
            self.device_cb, F.data.startswith("device_"), HelpStates.device_state
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
        await call.answer(text=f"Ты выбрал {call_device}", show_alert=False)
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
                    if hasattr(msg, "delete"):
                        await msg.delete()
                    await device_class.send_message(bot=self.bot, chat_id=chat_id)
                elif call_device == "developer":
                    if hasattr(msg, "delete"):
                        await msg.delete()
                    await self.bot.send_message(
                        text="Для связи напишите @BorisisTheBlade",
                        chat_id=chat_id,
                    )
        finally:
            await self.redis.delete(redis_key)
            await state.clear()
