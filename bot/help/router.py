from __future__ import annotations

from aiogram import Bot, F
from aiogram.filters import Command, StateFilter, and_f, or_f
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.config import settings_bot
from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.common_device import Device
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice
from bot.utils.base_router import BaseRouter

m_help = settings_bot.MESSAGES.get("modes", {}).get("help", {})


class HelpStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для команды /help."""

    device_state: State = State()


class HelpRouter(BaseRouter):
    """Роутер для обработки команды /help и выбора устройства."""

    DEVICE_MAP: dict[str, type[Device]] = {
        "android": AndroidDevice,
        "ios": IphoneDevice,
        "pc": PCDevice,
        "tv": TVDevice,
    }

    def __init__(self, bot: Bot, logger: Logger) -> None:
        super().__init__(bot, logger)

    def _register_handlers(self) -> None:
        self.router.message.register(
            self.help_cmd,
            or_f(Command("help"), F.text.contains("❓ Помощь в настройке VPN")),
            F.chat.type == "private",
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
                text=m_help.get("welcome", ""), reply_markup=ReplyKeyboardRemove()
            )
            start_block = m_help.get("start_block", [])
            for mess in start_block:
                if mess == start_block[-1]:
                    await message.answer(mess, reply_markup=device_keyboard())
                else:
                    await message.answer(mess)
        await state.set_state(HelpStates.device_state)

    @BaseRouter.log_method
    async def device_cb(self, call: CallbackQuery, state: FSMContext) -> None:
        """Обрабатывает выбор устройства пользователем.

        В зависимости от выбора (Android, iOS, PC, TV)
        вызывает соответствующий метод отправки инструкций.
        Очищается FSM

        Args:
            call (CallbackQuery): Объект callback-запроса от Telegram.
            state (FSMContext): Контекст конечного автомата состояний пользователя.

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=call.message.chat.id):
            call_device = call.data.replace("device_", "")
            await call.answer(text=f"Ты выбрал {call_device}", show_alert=False)
            device_class = self.DEVICE_MAP.get(call_device)
            if device_class:
                await device_class.send_message(
                    bot=self.bot, chat_id=call.message.chat.id
                )
            elif call_device == "developer":
                await call.message.delete()
                await call.bot.send_message(
                    text="Для связи напишите @BorisisTheBlade",
                    chat_id=call.message.chat.id,
                )
            await state.clear()
