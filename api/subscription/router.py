from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.core.dependencies import get_session
from api.subscription.dependencies import get_subscription_service
from api.subscription.schemas import (
    ActivateSubscriptionRequest,
    SSubscriptionCheck,
    STrialActivate,
    STrialActivateResponse,
)
from api.subscription.services import SubscriptionService
from api.users.schemas import SUserOut
from shared.enums.subscription_enum import TrialStatus

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
    premium, role, is_active, used_trial = await service.check_premium(
        session=session,
        tg_id=tg_id,
    )

    return SSubscriptionCheck(
        premium=premium, role=role, is_active=is_active, used_trial=used_trial
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
