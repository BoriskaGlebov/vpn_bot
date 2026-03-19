from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import get_session
from api.users.dependencies import get_user_service
from api.users.schemas import SUser, SUserOut
from api.users.services import UserService

router = APIRouter(prefix="/users", tags=["bot"])


@router.post("/register", response_model=SUserOut)
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
