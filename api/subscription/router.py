from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import get_session
from api.subscription.dependencies import (
    get_subscription_service,
)
from api.subscription.services import (
    SubscriptionService,
)
from shared.schemas.subscription import (
    ActivateSubscriptionRequest,
    SSubscriptionCheck,
    STrialActivate,
    STrialActivateResponse,
    TrialStatus,
)
from shared.schemas.users import SUserOut

router = APIRouter(prefix="/subscriptions", tags=["bot", "SUBSCRIPTION"])


@router.get(
    "/check/premium",
    response_model=SSubscriptionCheck,
    summary="Проверяет наличие премиум-подписки",
)
async def check_premium(
    tg_id: int,
    session: AsyncSession = Depends(get_session),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SSubscriptionCheck:
    """Проверяет наличие активной премиум-подписки.

    Args:
        tg_id: Telegram ID пользователя.
        session: DB session dependency.
        service: Subscription service.

    Returns
        SSubscriptionCheck: статус подписки, роль и активность.

    """
    premium, role, is_active = await service.check_premium(
        session=session,
        tg_id=tg_id,
    )

    return SSubscriptionCheck(
        premium=premium,
        role=role,
        is_active=is_active,
    )


@router.post(
    "/trial/activate",
    status_code=status.HTTP_201_CREATED,
    response_model=STrialActivateResponse,
    summary="Активация пробного периода подписки",
)
async def start_trial(
    data: STrialActivate,
    session: AsyncSession = Depends(get_session),
    service: SubscriptionService = Depends(get_subscription_service),
) -> STrialActivateResponse:
    """Активирует trial-подписку пользователя.

    Args:
        data: входные данные (tg_id, days)
        session: DB session
        service: business logic service

    Returns
        STrialActivateResponse: статус активации trial

    Raises
        ActiveSubscriptionExistsError
        TrialAlreadyUsedError

    """
    await service.start_trial_subscription(
        session=session,
        tg_id=data.tg_id,
        days=data.days,
    )
    return STrialActivateResponse(
        status=TrialStatus.STARTED,
    )


@router.post(
    "/activate",
    response_model=SUserOut,
    status_code=status.HTTP_200_OK,
    summary="Активация платной подписки",
)
async def activate_subscription(
    data: ActivateSubscriptionRequest,
    session: AsyncSession = Depends(get_session),
    service: SubscriptionService = Depends(get_subscription_service),
) -> SUserOut:
    """Активирует или продлевает платную подписку пользователя.

    Args:
        data: запрос (tg_id, months, premium)
        session: DB session
        service: бизнес-логика подписок

    Returns
        SUserOut: обновлённый пользователь

    """
    return await service.activate_paid_subscription(
        session=session,
        user_id=data.tg_id,
        months=data.months,
        premium=data.premium,
    )


#
#
# def map_event_to_schema(event: SubscriptionEvent):
#     if isinstance(event, UserNotifyEvent):
#         return UserNotifyEventSchema(
#             type="user_notify",
#             user_id=event.user_id,
#             message=event.message,
#         )
#
#     if isinstance(event, DeleteVPNConfigsEvent):
#         return DeleteVPNConfigsEventSchema(
#             type="delete_vpn_configs",
#             user_id=event.user_id,
#             configs=event.configs,
#         )
#
#     if isinstance(event, DeleteProxyEvent):
#         return DeleteProxyEventSchema(
#             type="delete_proxy",
#             user_id=event.user_id,
#         )
#
#     if isinstance(event, AdminNotifyEvent):
#         return AdminNotifyEventSchema(
#             type="admin_notify",
#             user_id=event.user_id,
#             message=event.message,
#         )
#
#     raise ValueError(f"Unknown event: {event}")
#
#
# @router.post(
#     "/check-all",
#     response_model=CheckAllSubscriptionsResponse,
#     summary="Проверяет подписки пользователей и возвращает список действий для бота",
# )
# async def check_all(
#     session: AsyncSession = Depends(get_session),
#     service: SubscriptionScheduler = Depends(get_subscription_scheduler_service),
# ):
#     stats, events = await service.check_all_subscriptions(
#         session=session,
#     )
#
#     return CheckAllSubscriptionsResponse(
#         stats=SubscriptionStatsSchema(
#             checked=stats.checked,
#             expired=stats.expired,
#             notified=0,
#             configs_deleted=stats.configs_deleted,
#         ),
#         events=[map_event_to_schema(e) for e in events],
#     )
