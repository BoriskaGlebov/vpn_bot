from aiogram.dispatcher.router import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from loguru import logger

from bot.config import settings_bot
from bot.utils.commands import admin_commands, user_commands

help_router = Router()


@help_router.message(Command("help"))  # type: ignore
async def help_cmd(message: Message, state: FSMContext) -> None:
    """Обрабатывает команду /help и отправляет пользователю список доступных команд.

    Показывает разные команды для обычных пользователей и администраторов.
    """
    try:
        command_list = [
            f"/{cmd.command} - {cmd.description}"
            for cmd in (
                admin_commands
                if message.from_user.id in settings_bot.ADMIN_IDS
                else user_commands
            )
        ]

        await state.clear()

        await message.answer(
            text="\n".join(command_list), reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении команды /help: {e}")
        await message.answer(settings_bot.MESSAGES["general"]["common_error"])
