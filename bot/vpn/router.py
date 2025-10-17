from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from config import bot
from database import connection
from sqlalchemy.ext.asyncio import AsyncSession
from users.dao import UserDAO
from users.router import UserStates
from users.schemas import SUserTelegramID

vpn_router = Router()


# class VPNStates(StatesGroup):
#     """Состояния FSM для vpn-router."""
#
#     pass


@vpn_router.message(
    UserStates.press_start, F.text.contains("🔑 Получить VPN-конфиг AmneziaVPN")
)  # type: ignore[misc]
async def get_config_amnezia_vpn(message: Message, state: FSMContext) -> None:
    """Пользователь получит конфиг файл amnezia_vpn."""
    await message.answer(
        "На свой конфиг amneziaVPN", reply_markup=ReplyKeyboardRemove()
    )
    await state.clear()


@vpn_router.message(
    UserStates.press_start, F.text.contains("🌐 Получить VPN-конфиг AmneziaWG")
)  # type: ignore[misc]
async def get_config_amnezia_wg(message: Message, state: FSMContext) -> None:
    """Пользвоатель получит конфиг Amnezia WG."""
    await message.answer("На свой конфиг amneziaWG", reply_markup=ReplyKeyboardRemove())
    await state.clear()


@vpn_router.message(
    UserStates.press_start, F.text.contains("📈 Проверить статус подписки")
)  # type: ignore[misc]
@connection()  # type: ignore[misc]
async def check_subscription(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Проверка статуса подписки пользователем."""
    s_user = SUserTelegramID(telegram_id=message.from_user.id)
    user = await UserDAO.find_one_or_none(session=session, filters=s_user)
    await message.answer(
        "Проверка статуса подписки", reply_markup=ReplyKeyboardRemove()
    )
    print(user.subscription)
    await bot.send_message(chat_id=message.from_user.id, text=str(user.subscription))
    await state.clear()
