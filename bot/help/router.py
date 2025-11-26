from __future__ import annotations

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from loguru._logger import Logger

from bot.config import settings_bot
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
        pass

    @BaseRouter.log_method
    async def help_cmd(self, message: Message, state: FSMContext) -> None:
        pass

    @BaseRouter.log_method
    async def device_cb(self, call: CallbackQuery, state: FSMContext) -> None:
        pass
