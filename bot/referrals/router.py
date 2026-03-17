from aiogram import Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.types import User as TGUser
from loguru._logger import Logger

from bot.config import settings_bot
from bot.utils.base_router import BaseRouter

m_referrals = settings_bot.messages.modes.referrals


class ReferralRouter(BaseRouter):
    """Router, отвечающий за реферальную функциональность.

    Регистрирует команды, связанные с приглашением друзей, и
    формирует сообщения с персональной реферальной ссылкой.
    """

    def __init__(self, bot: Bot, logger: Logger) -> None:
        super().__init__(bot, logger)

    def _register_handlers(self) -> None:
        self.router.message.register(self.invite_handler, Command("friends"))

    @BaseRouter.log_method
    @BaseRouter.require_user
    async def invite_handler(
        self, message: Message, user: TGUser, state: FSMContext
    ) -> None:
        """Обрабатывает команду приглашения друзей.

        Формирует персональную реферальную ссылку пользователя и
        отправляет сообщение с inline-кнопкой для её распространения.

        Args:
            user: Пользователь для работы
            message (Message): Входящее сообщение от пользователя.
            state (FSMContext):Машина состояния.

        """
        await state.clear()
        bot = await self.bot.get_me()
        ref_link = f"https://t.me/{bot.username}?start=ref_{user.id}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📨 Долгое нажатие > скопировать ссылку",
                        url=ref_link,
                    )
                ]
            ]
        )

        await message.answer(
            text=m_referrals.invite,
            reply_markup=keyboard,
        )
