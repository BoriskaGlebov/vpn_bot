from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import (
    get_current_user,
    get_session,
    verify_internal_secret,
)
from api.core.openapi_responses import AUTH_RESPONSES
from api.users.dependencies import get_user_service
from api.users.models import User
from api.users.schemas import SUser, SUserOut, SUserWithReferralStats
from api.users.services import UserService

router = APIRouter(prefix="/users", tags=["bot", "USERS"])


@router.post(
    "/register",
    response_model=SUserOut,
    summary="Регистрирует пользователя или возвращает существующего.",
    responses=AUTH_RESPONSES,
)
async def register_user(
    user_data: SUser,
    response: Response,
    session: AsyncSession = Depends(get_session),
    service: UserService = Depends(get_user_service),
    _: None = Depends(verify_internal_secret),
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
    responses=AUTH_RESPONSES,
)
async def get_user_referrals(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    service: UserService = Depends(get_user_service),
    user_auth: User = Depends(get_current_user),
) -> SUserWithReferralStats:
    """Возвращает пользователя с реферальной статистикой.

    Включает referrals_count, paid_referrals_count, referral_conversion.

    Args:
        telegram_id (int): Telegram ID пользователя.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (UserService): Сервис для работы с пользователями.
        user_auth (User): Проверка,что пользователь зарегистрирован.

    Returns
        SUserWithReferralStats: DTO пользователя с реферальной статистикой.

    Raises
        UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

    """
    user_with_referrals = await service.get_user_with_referrals(
        session=session,
        telegram_id=telegram_id,
    )

    return user_with_referrals
