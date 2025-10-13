from aiogram import F
from aiogram.dispatcher.router import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender

from bot.config import bot, settings_bot
from bot.help.keyboards.inline_kb import device_keyboard
from bot.help.utils.android_device import AndroidDevice
from bot.help.utils.iphone_device import IphoneDevice
from bot.help.utils.pc_device import PCDevice
from bot.help.utils.tv_device import TVDevice

help_router = Router()

m_help = settings_bot.MESSAGES["modes"]["help"]


class HelpStates(StatesGroup):  # type: ignore[misc]
    """Состояния FSM для команды /help."""

    cmd_help: State = State()
    device_state: State = State()


@help_router.message(Command("help"))  # type: ignore
@help_router.message(F.text.contains("❓ Помощь в настройке VPN"))  # type: ignore[misc]
async def help_cmd(message: Message, state: FSMContext) -> None:
    """Обрабатывает команду /help и показывает пользователю первый блок помощи.

    Переходит в состояние выбора устройства, после чего
    отправляет пользователю соответствующие инструкции.

    Args:
        message (Message): Объект сообщения Telegram.
        state (FSMContext): Контекст конечного автомата состояний пользователя.

    """
    await state.set_state(HelpStates.cmd_help)
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        await message.answer(
            "🚀 Супер, что выбрали этот пункт", reply_markup=ReplyKeyboardRemove()
        )
        for mess in m_help["start_block"]:
            if mess == m_help["start_block"][-1]:
                await message.answer(mess, reply_markup=device_keyboard())
            else:
                await message.answer(mess)
    await state.set_state(HelpStates.device_state)


@help_router.callback_query(F.data.startswith("device_"), HelpStates.device_state)  # type: ignore[misc]
async def device_cb(call: CallbackQuery, state: FSMContext) -> None:
    """Обрабатывает выбор устройства пользователем.

    В зависимости от выбора (Android, iOS, PC, TV)
    вызывает соответствующий метод отправки инструкций.
    Очищается FSM

    Args:
        call (CallbackQuery): Объект callback-запроса от Telegram.
        state (FSMContext): Контекст конечного автомата состояний пользователя.

    """
    async with ChatActionSender.typing(bot=bot, chat_id=call.message.chat.id):
        call_device = call.data.replace("device_", "")
        await call.answer(text=f"Ты выбрал {call_device}", show_alert=False)
        if call_device == "android":
            await AndroidDevice.send_message(bot, call.message.chat.id)
        elif call_device == "ios":
            await IphoneDevice.send_message(bot, call.message.chat.id)
        elif call_device == "pc":
            await PCDevice.send_message(bot, call.message.chat.id)
        elif call_device == "tv":
            await TVDevice.send_message(bot, call.message.chat.id)
        await state.clear()
