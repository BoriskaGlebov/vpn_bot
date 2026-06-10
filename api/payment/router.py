from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_current_user, get_session
from api.payment.schemas import (
    SCancelPayment,
    SCancelPaymentIn,
    SConfirmPayment,
    SConfirmPaymentIn,
    SConfirmPaymentResponse,
    SCreateManualPaymentTransaction,
    SPaymentTransactionResponse,
)
from api.payment.services import PaymentService
from api.referrals.schemas import GrantReferralBonusResponse
from api.referrals.services import ReferralService
from api.subscription.services import SubscriptionService
from api.users.models import User

# TODO нужно не забыть про документацию для api
router = APIRouter(prefix="/payment", tags=["bot", "PAYMENT"])


#
@router.post(
    "/transaction",
    response_model=SPaymentTransactionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создание платежной транзакции",
    description=(
        "Создает новую платежную транзакцию для текущего авторизованного пользователя."
    ),
    response_description="Созданная платежная транзакция.",
)
async def create_transaction(
    transaction: SCreateManualPaymentTransaction,
    service: PaymentService = Depends(PaymentService),
    user_auth: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:
    """Создание новой платежной транзакции.

    Endpoint используется для создания платежа
    текущим авторизованным пользователем.

    Args:
        transaction:
            Данные создаваемой транзакции.

        service:
            Сервис платежных транзакций.

        user_auth:
            Текущий авторизованный пользователь.

        session:
            Асинхронная SQLAlchemy-сессия.

    Returns
        Созданная платежная транзакция.

    """
    res = await service.create_transaction(
        session=session, transaction=transaction, user_auth=user_auth
    )
    return res


@router.post(
    "/transaction/confirm",
    response_model=SConfirmPaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Подтверждение платежа",
    description=(
        "Подтверждает платежную транзакцию администратором, "
        "активирует подписку пользователя и начисляет "
        "реферальный бонус при наличии реферальной связи."
    ),
    response_description=(
        "Результат подтверждения платежа, активации подписки и начисления бонуса."
    ),
)
async def confirm_transaction(
    data: SConfirmPaymentIn,
    service: PaymentService = Depends(PaymentService),
    sub_service: SubscriptionService = Depends(SubscriptionService),
    ref_service: ReferralService = Depends(ReferralService),
    admin_auth: User = Depends(check_admin_role),
    session: AsyncSession = Depends(get_session),
) -> SConfirmPaymentResponse:
    """Подтверждение платежной транзакции.

    После подтверждения:
        - транзакция переводится в статус ``PAID``;
        - активируется подписка пользователя;
        - начисляется реферальный бонус.

    Args:
        data:
            Данные подтверждаемой транзакции.

        service:
            Сервис платежных транзакций.

        sub_service:
            Сервис подписок.

        ref_service:
            Сервис реферальной системы.

        admin_auth:
            Текущий администратор.

        session:
            Асинхронная SQLAlchemy-сессия.

    Returns
        Результат подтверждения платежа.

    """
    conf_payment = SConfirmPayment(
        admin_id=admin_auth.id, transaction_id=data.transaction_id
    )
    tx = await service.confirm_transaction(session=session, data=conf_payment)
    sub_res = await sub_service.activate_paid_subscription(
        session=session,
        user_id=tx.tg_id,
        months=tx.subscription_months,
        premium=tx.is_premium,
    )
    ref_res, inviter, message = await ref_service.grant_referral_bonus(
        session=session,
        invited_user=sub_res,
    )
    return SConfirmPaymentResponse(
        transaction_res=tx,
        subscription_res=sub_res,
        referral_res=GrantReferralBonusResponse(
            success=ref_res,
            inviter_telegram_id=inviter,
            message=message,
        ),
    )


@router.post(
    "/transaction/cancel",
    response_model=SPaymentTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Отмена платежной транзакции",
    description=("Отменяет платежную транзакцию. Доступно только администраторам."),
    response_description="Обновленная платежная транзакция.",
)
async def cancel_transaction(
    data: SCancelPaymentIn,
    service: PaymentService = Depends(PaymentService),
    admin_auth: User = Depends(check_admin_role),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:
    """Отмена платежной транзакции.

    Endpoint переводит транзакцию
    в статус ``CANCELED``.

    Args:
        data:
            Данные отменяемой транзакции.

        service:
            Сервис платежных транзакций.

        admin_auth:
            Текущий администратор.

        session:
            Асинхронная SQLAlchemy-сессия.

    Returns
        Обновленная платежная транзакция.

    """
    cancel_data = SCancelPayment(
        transaction_id=data.transaction_id,
        admin_id=admin_auth.id,
    )

    res = await service.cancel_transaction(
        session=session,
        data=cancel_data,
    )

    return res
