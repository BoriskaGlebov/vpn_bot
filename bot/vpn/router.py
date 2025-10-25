from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import bot
from bot.database import connection
from bot.users.dao import UserDAO
from bot.users.schemas import SUserTelegramID

if TYPE_CHECKING:
    pass
vpn_router = Router()


# class VPNStates(StatesGroup):
#     """Состояния FSM для vpn-router."""
#
#     pass


class VPNRouter:
    """Роутер для обработки команд VPN."""

    def __init__(self) -> None:
        self.router = Router(name="vpn_router")
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Регистрация хендлеров."""
        self.router.message.register(
            self.get_config_amnezia_vpn,
            F.text.contains("🔑 Получить VPN-конфиг AmneziaVPN"),
        )
        self.router.message.register(
            self.get_config_amnezia_wg,
            F.text.contains("🌐 Получить VPN-конфиг AmneziaWG"),
        )
        self.router.message.register(
            self.check_subscription,
            F.text.contains("📈 Проверить статус подписки"),
        )

    @staticmethod
    async def get_config_amnezia_vpn(message: Message, state: FSMContext) -> None:
        """Пользователь получает конфиг AmneziaVPN."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            await message.answer(
                "На свой конфиг amneziaVPN", reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()

    @staticmethod
    async def get_config_amnezia_wg(message: Message, state: FSMContext) -> None:
        """Пользователь получает конфиг AmneziaWG."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            await message.answer(
                "На свой конфиг amneziaWG", reply_markup=ReplyKeyboardRemove()
            )
            await state.clear()

    @staticmethod
    @connection()
    async def check_subscription(
        message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        """Проверка статуса подписки пользователя."""
        async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
            s_user = SUserTelegramID(telegram_id=message.from_user.id)
            user = await UserDAO.find_one_or_none(session=session, filters=s_user)
            if user is None:
                raise ValueError(f"Не удалось найти пользователя {s_user.telegram_id}")

            await message.answer(
                "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
            )

            text = (
                f"✅ {user.subscription}"
                if user.subscription.is_active
                else f"🔒 {user.subscription}"
            )

            await bot.send_message(chat_id=message.from_user.id, text=text)
            await state.clear()


#
# @vpn_router.message(F.text.contains("🔑 Получить VPN-конфиг AmneziaVPN"))  # type: ignore[misc]
# async def get_config_amnezia_vpn(message: Message, state: FSMContext) -> None:
#     """Пользователь получит конфиг файл amnezia_vpn."""
#     async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
#         await message.answer(
#             "На свой конфиг amneziaVPN", reply_markup=ReplyKeyboardRemove()
#         )
#         await state.clear()
#
#
# @vpn_router.message(F.text.contains("🌐 Получить VPN-конфиг AmneziaWG"))  # type: ignore[misc]
# async def get_config_amnezia_wg(message: Message, state: FSMContext) -> None:
#     """Пользвоатель получит конфиг Amnezia WG."""
#     async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
#         await message.answer(
#             "На свой конфиг amneziaWG", reply_markup=ReplyKeyboardRemove()
#         )
#         await state.clear()
#
#
# @vpn_router.message(F.text.contains("📈 Проверить статус подписки"))  # type: ignore[misc]
# @connection()
# async def check_subscription(
#     message: Message, session: AsyncSession, state: FSMContext
# ) -> None:
#     """Проверка статуса подписки пользователем."""
#     async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
#         s_user = SUserTelegramID(telegram_id=message.from_user.id)
#         user = await UserDAO.find_one_or_none(session=session, filters=s_user)
#         if user is None:
#             raise ValueError(f"Не удалось найти пользователя {s_user.telegram_id} ")
#         await message.answer(
#             "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
#         )
#         if user.subscription.is_active:
#             text = f"✅ {user.subscription}"
#         else:
#             text = f"🔒 {user.subscription}"
#
#         await bot.send_message(chat_id=message.from_user.id, text=text)
#         await state.clear()
