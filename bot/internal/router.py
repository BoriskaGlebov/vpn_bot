"""Внутренний HTTP-канал api → bot.

`api/` не имеет доступа к VPN-панелям/нодам (туда ходит только `bot/`), поэтому
команды, требующие действий на нодах (например, отзыв доступа при удалении
пользователя/конфига в админке), api отправляет сюда. Все эндпоинты защищены
ключом `X-API-Key` (`verify_internal_api_key`), а не Telegram-контекстом.
"""

from fastapi import APIRouter, Depends
from loguru import logger

from bot.app_error.base_error import VPNConfigDeletionFailedError
from bot.internal.dependencies import get_vpn_service, verify_internal_api_key
from bot.internal.schemas import SRevokeConfigRequest, SRevokeConfigResponse
from bot.vpn.services import VPNService
from shared.enums.vpn_enum import VPNRevokeStatus

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_api_key)],
)


@router.post(
    "/vpn/revoke",
    response_model=SRevokeConfigResponse,
    summary="Отозвать доступ VPN-конфига на нодах",
)
async def revoke_vpn_config(
    payload: SRevokeConfigRequest,
    vpn_service: VPNService = Depends(get_vpn_service),
) -> SRevokeConfigResponse:
    """Удаляет конфиг на ноде/панели, не трогая запись в БД.

    Запись в БД удаляет вызывающая сторона (`api/`) — и только если исход
    `ok` или `not_found`. Исход всегда возвращается телом ответа с HTTP 200,
    чтобы отличать его от сбоев транспорта/авторизации (4xx/5xx).

    Args:
        payload: Владелец и конфиг для отзыва.
        vpn_service: Сервис VPN.

    Returns
        SRevokeConfigResponse: `ok` — удалён на ноде; `not_found` — на нодах
        его уже нет; `node_error` — нода недоступна, запись в БД удалять нельзя.

    """
    config = payload.config
    logger.info(
        "Получен запрос api → bot: отозвать конфиг {} (tg_id={}, node={})",
        config.file_name,
        payload.tg_id,
        config.node_name,
    )
    try:
        revoked = await vpn_service.revoke_config_access(config)
    except VPNConfigDeletionFailedError as exc:
        logger.error(
            "Отзыв доступа конфига {} (tg_id={}) не удался: нода/панель недоступна",
            config.file_name,
            payload.tg_id,
        )
        return SRevokeConfigResponse(
            status=VPNRevokeStatus.NODE_ERROR, detail=exc.message
        )

    if not revoked:
        logger.warning(
            "Конфиг {} (tg_id={}) не найден на нодах при отзыве доступа",
            config.file_name,
            payload.tg_id,
        )
        return SRevokeConfigResponse(status=VPNRevokeStatus.NOT_FOUND)

    logger.info("Доступ конфига {} (tg_id={}) отозван", config.file_name, payload.tg_id)
    return SRevokeConfigResponse(status=VPNRevokeStatus.OK)
