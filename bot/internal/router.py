"""Внутренний HTTP-канал api → bot.

`api/` не имеет доступа к VPN-панелям/нодам (туда ходит только `bot/`), поэтому
команды, требующие действий на нодах (например, отзыв доступа при удалении
пользователя/конфига в админке), api отправляет сюда. Все эндпоинты защищены
ключом `X-API-Key` (`verify_internal_api_key`), а не Telegram-контекстом.
"""

from fastapi import APIRouter, Depends
from loguru import logger

from bot.app_error.base_error import VPNConfigDeletionFailedError
from bot.internal.dependencies import (
    get_admin_broadcast_service,
    get_vpn_service,
    verify_internal_api_key,
)
from bot.internal.schemas import (
    SBroadcastRequest,
    SBroadcastResponse,
    SRevokeConfigRequest,
    SRevokeConfigResponse,
)
from bot.news.services import BroadcastService
from bot.utils.background import run_in_background
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


@router.post(
    "/broadcast",
    response_model=SBroadcastResponse,
    summary="Разослать текст выбранным получателям",
)
async def broadcast(
    payload: SBroadcastRequest,
    broadcast_service: BroadcastService = Depends(get_admin_broadcast_service),
) -> SBroadcastResponse:
    """Запускает в фоне рассылку текста отмеченным в админке пользователям.

    Не блокирует ответ api на тысячах получателей — рассылка идёт в фоне
    (переиспользует инфраструктуру новостей, `BroadcastService`), а итог
    (доставлено/не доставлено) бот присылает в админ-чат отдельным
    сообщением (`send_to_admins`).

    Args:
        payload: Текст рассылки и telegram_id получателей.
        broadcast_service: Сервис рассылки по выбранным пользователям.

    Returns
        SBroadcastResponse: Подтверждение приёма команды (не итог рассылки).

    """
    logger.info(
        "Получен запрос api → bot: рассылка по {} выбранным пользователям",
        len(payload.recipients),
    )
    run_in_background(
        broadcast_service.broadcast_to_all(
            content={"content_type": "text", "text": payload.text},
            recipients=payload.recipients,
            initiated_by="admin-panel",
            preview=payload.text,
            notify_always=True,
        ),
        logger=logger,  # type: ignore[arg-type]
        error_message="Фоновая рассылка по выбранным пользователям упала",
    )
    return SBroadcastResponse(accepted=True, recipients=len(payload.recipients))
