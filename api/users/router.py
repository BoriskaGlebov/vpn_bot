from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.app_error.base_error import UserNotFoundError
from api.core.dependencies import get_current_user, get_session
from api.users.dependencies import get_user_service
from api.users.models import User
from api.users.schemas import SUser, SUserOut, SUserWithReferralStats
from api.users.services import UserService

router = APIRouter(prefix="/users", tags=["bot", "USERS"])


@router.post(
    "/register",
    response_model=SUserOut,
    summary="Регистрирует пользователя или возвращает существующего.",
)
async def register_user(
    user_data: SUser,
    response: Response,
    session: AsyncSession = Depends(get_session),
    service: UserService = Depends(get_user_service),
) -> SUserOut:
    """Регистрирует пользователя или возвращает существующего.

    Если пользователь с переданным Telegram ID отсутствует в базе,
    создаётся новая запись и возвращается статус HTTP 201 (Created).
    Если пользователь уже существует — возвращается статус HTTP 200 (OK).

    Args:
        user_data (SUser): Данные пользователя (Telegram ID, username и т.д.).
        response (Response): Объект ответа FastAPI для установки статус-кода.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (UserService): Сервис для работы с пользователями.

    Returns
        SUserOut: Данные пользователя в формате ответа API.

    """
    user, created = await service.register_or_get_user(
        session=session,
        telegram_user=user_data,
    )

    if created:
        response.status_code = status.HTTP_201_CREATED

    return user


@router.get(
    "/{telegram_id}/referrals",
    response_model=SUserWithReferralStats,
    summary="Получает пользователя с реферальной статистикой",
)
async def get_user_referrals(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    service: UserService = Depends(get_user_service),
    user_auth: User = Depends(get_current_user),
) -> SUserWithReferralStats:
    """Возвращает пользователя с реферальной статистикой.

    Выполняет получение пользователя по Telegram ID и рассчитывает
    агрегированную статистику по рефералам.

    Args:
        telegram_id (int): Telegram ID пользователя.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (UserService): Сервис для работы с пользователями.
        user_auth (User): Проверка,что пользователь зарегистрирован.

    Returns
        SUserWithReferralStats: DTO пользователя, включающий:
            - referrals_count (int): Общее количество рефералов.
            - paid_referrals_count (int): Количество рефералов с оплатой.
            - referral_conversion (float): Конверсия (paid / total).

    Raises
        UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

    """
    user_with_referrals = await service.get_user_with_referrals(
        session=session,
        telegram_id=telegram_id,
    )

    if not user_with_referrals:
        raise UserNotFoundError(tg_id=telegram_id)

    return user_with_referrals
