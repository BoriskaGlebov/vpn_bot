from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import get_current_user, get_session
from api.users.models import User
from api.vpn.dependencies import get_vpn_service
from api.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateRequest,
    SVPNCreateResponse,
    SVPNDeleteRequest,
    SVPNDeleteResponse,
)
from api.vpn.services import VPNService

router = APIRouter(prefix="/vpn", tags=["bot", "VPN"])


@router.get(
    "/limit",
    response_model=SVPNCheckLimitResponse,
    summary="Проверка лимита VPN конфигов",
)
async def check_limit(
    tg_id: int,
    session: AsyncSession = Depends(get_session),
    service: VPNService = Depends(get_vpn_service),
    user_auth: User = Depends(get_current_user),
) -> SVPNCheckLimitResponse:
    """Проверяет, может ли пользователь создать новый VPN конфиг.

    Args:
        tg_id (int): Telegram ID пользователя.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (VPNService): Сервис для работы с VPN.
        user_auth (User): Текущий авторизованный пользователь (через dependency).

    Returns
        SVPNCheckLimitResponse: Информация о лимите VPN конфигов.

    """
    return await service.check_limit(
        session=session,
        tg_id=tg_id,
    )


@router.post(
    "/config",
    response_model=SVPNCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Сохранение VPN конфига",
)
async def add_config(
    data: SVPNCreateRequest,
    session: AsyncSession = Depends(get_session),
    service: VPNService = Depends(get_vpn_service),
    user_auth: User = Depends(get_current_user),
) -> SVPNCreateResponse:
    """Сохраняет новый VPN конфиг в базе данных.

    Args:
        data (SVPNCreateRequest): Данные конфига (tg_id, file_name, pub_key).
        session (AsyncSession): Асинхронная сессия базы данных.
        service (VPNService): Сервис для работы с VPN.
        user_auth (User): Текущий авторизованный пользователь (через dependency).

    Returns
        SVPNCreateResponse: Информация о созданном конфиге.

    """
    return await service.add_config(
        session=session,
        tg_id=data.tg_id,
        file_name=data.file_name,
        pub_key=data.pub_key,
    )


@router.delete(
    "/config",
    status_code=status.HTTP_200_OK,
    summary="Удаление VPN конфига",
)
async def delete_config(
    data: SVPNDeleteRequest,
    session: AsyncSession = Depends(get_session),
    service: VPNService = Depends(get_vpn_service),
    user_auth: User = Depends(get_current_user),
) -> SVPNDeleteResponse:
    """Удаляет VPN конфиг по имени файла и публичному ключу.

    Args:
        data (SVPNDeleteRequest): Данные конфига (file_name и pub_key).
        session (AsyncSession): Асинхронная сессия базы данных.
        service (VPNService): Сервис для работы с VPN.
        user_auth (User): Текущий авторизованный пользователь (через dependency).

    Returns
        SVPNDeleteResponse: Количество удалённых конфигов.

    """
    deleted = await service.delete_config(
        session=session,
        file_name=data.file_name,
        pub_key=data.pub_key,
    )
    return SVPNDeleteResponse(deleted=deleted)
