from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import UserNotFoundError
from api.core.dependencies import get_session
from api.core.mapper.user_mapper import UserMapper
from api.referrals.dependencies import get_referral_service
from api.referrals.services import ReferralService
from api.users.dao import UserDAO
from shared.schemas.referral import (
    GrantReferralBonusRequest,
    GrantReferralBonusResponse,
    RegisterReferralRequest,
    RegisterReferralResponse,
)
from shared.schemas.users import SUserTelegramID

router = APIRouter(prefix="/referrals", tags=["bot"])


@router.post(
    "/register",
    response_model=RegisterReferralResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Регистрация реферала",
    description="Регистрирует связь между пригласившим и приглашённым пользователем.",
    responses={
        201: {
            "description": "Реферал успешно зарегистрирован",
            "model": RegisterReferralResponse,
        },
        404: {
            "description": "Приглашённый пользователь не найден",
        },
        400: {
            "description": "Ошибка запроса",
        },
    },
)
async def register_referral(
    payload: RegisterReferralRequest,
    session: AsyncSession = Depends(get_session),
    service: ReferralService = Depends(get_referral_service),
) -> RegisterReferralResponse:
    """Регистрирует реферальную связь между пользователями.

    Args:
        payload (RegisterReferralRequest): Данные для регистрации реферала.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (ReferralService): Сервис реферальной системы.

    Returns
        RegisterReferralResponse: Результат регистрации реферала.

    Raises
        UserNotFoundError: Если приглашённый пользователь не найден.

    HTTP статус-коды:
        201: Реферал успешно зарегистрирован
        404: Пользователь не найден
        500: Ошибка запроса базы данных

    """
    invited_user = await UserDAO.find_one_or_none(
        session=session,
        filters=SUserTelegramID(telegram_id=payload.invited_user_id),
    )

    if not invited_user:
        raise UserNotFoundError(tg_id=payload.invited_user_id)

    suser_res = await UserMapper.to_schema(invited_user)

    await service.register_referral(
        session=session,
        invited_user=suser_res,
        inviter_telegram_id=payload.inviter_telegram_id,
    )

    return RegisterReferralResponse(
        success=True,
        message="Реферал зарегистрирован успешно.",
    )


@router.post(
    "/bonus",
    response_model=GrantReferralBonusResponse,
    status_code=status.HTTP_200_OK,
    summary="Начисление бонуса за реферала",
    description="Начисляет бонус пригласителю за приглашённого пользователя.",
    responses={
        200: {
            "description": "Бонус успешно начислен",
            "model": GrantReferralBonusResponse,
        },
        404: {
            "description": "Приглашённый пользователь или реферал не найден",
        },
        409: {
            "description": "Бонус уже был начислен ранее",
        },
        400: {
            "description": "Ошибка запроса",
        },
    },
)
async def grant_bonus(
    payload: GrantReferralBonusRequest,
    session: AsyncSession = Depends(get_session),
    service: ReferralService = Depends(get_referral_service),
) -> GrantReferralBonusResponse:
    """Начисляет бонус за приглашённого пользователя.

    Args:
        payload (GrantReferralBonusRequest): Данные для начисления бонуса.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (ReferralService): Сервис реферальной системы.

    Returns
        GrantReferralBonusResponse: Результат операции начисления бонуса.

    Raises
        UserNotFoundError: Если приглашённый пользователь не найден.

    HTTP статус-коды:
        200: Бонус успешно начислен
        404: Пользователь или реферал не найден
        409: Бонус уже начислен
        400: Ошибка запроса

    """
    invited_user = await UserDAO.find_one_or_none(
        session=session,
        filters=SUserTelegramID(telegram_id=payload.invited_user_id),
    )

    if not invited_user:
        raise UserNotFoundError(tg_id=payload.invited_user_id)

    suser_res = await UserMapper.to_schema(invited_user)

    success, inviter_telegram_id = await service.grant_referral_bonus(
        session=session,
        invited_user=suser_res,
        months=payload.months,
    )

    return GrantReferralBonusResponse(
        success=success,
        inviter_telegram_id=inviter_telegram_id,
        message="Referral bonus granted successfully",
    )
