from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import get_session
from api.vpn.dependencies import get_vpn_service
from api.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateRequest,
    SVPNCreateResponse,
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
) -> SVPNCheckLimitResponse:
    """Проверяет, может ли пользователь создать новый VPN конфиг."""
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
) -> SVPNCreateResponse:
    """Сохраняет новый VPN конфиг в БД."""
    return await service.add_config(
        session=session,
        tg_id=data.tg_id,
        file_name=data.file_name,
        pub_key=data.pub_key,
    )
