from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import check_admin_role
from api.payment.schemas import SCreateManualPaymentTransaction, SPaymentTransactionResponse, SConfirmPayment, \
    SConfirmPaymentIn, SCancelPaymentIn, SCancelPayment
from api.core.dependencies import get_current_user, get_session
from api.payment.services import PaymentService
from api.users.models import User

#TODO нужно не забыть про документацию для api
router = APIRouter(prefix="/payment", tags=["bot", "PAYMENT"])

#
@router.post("/transaction")
async def create_transaction(transaction:SCreateManualPaymentTransaction,
                             service:PaymentService = Depends(PaymentService),
                             user_auth: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)
                             )->SPaymentTransactionResponse:
    res=await service.create_transaction(session=session,transaction=transaction,user_auth=user_auth)
    return res

@router.post("/transaction/confirm")
async def confirm_transaction(
    data: SConfirmPaymentIn,
    service:PaymentService = Depends(PaymentService),
    admin_auth: User = Depends(check_admin_role),
    session: AsyncSession = Depends(get_session)
)->SPaymentTransactionResponse:
    conf_payment=SConfirmPayment(admin_id=admin_auth.id,transaction_id=data.transaction_id)
    res=await service.confirm_transaction(session=session,data=conf_payment)
    return res

@router.post("/transaction/cancel")
async def cancel_transaction(
    data: SCancelPaymentIn,
    service: PaymentService = Depends(PaymentService),
    admin_auth: User = Depends(check_admin_role),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:

    cancel_data = SCancelPayment(
        transaction_id=data.transaction_id,
        admin_id=admin_auth.id,
    )

    res = await service.cancel_transaction(
        session=session,
        data=cancel_data,
    )

    return res

# async def cheturn Noneeck_premium(
#     tg_id: int,
#     session: AsyncSession = Depends(get_session),
#     service: SubscriptionService = Depends(get_subscription_service),
#     user_auth: User = Depends(get_current_user),
# ) -> SSubscriptionCheck:
#     """Проверяет наличие активной премиум-подписки.
#
#     Args:
#         tg_id: Telegram ID пользователя.
#         session: DB session dependency.
#         service: Subscription service.
#         user_auth (User): Проверка,что пользователь зарегистрирован.
#
#     Returns
#         SSubscriptionCheck: статус подписки, роль и активность.
#
#     """
#     premium, role, is_active, used_trial = await service.check_premium(
#         session=session,
#         tg_id=tg_id,
#     )
#
#     return SSubscriptionCheck(
#         premium=premium, role=role, is_active=is_active, used_trial=used_trial
#     )
#
#
# @router.post(
#     "/trial/activate",
#     status_code=status.HTTP_201_CREATED,
#     response_model=STrialActivateResponse,
#     summary="Активация пробного периода подписки",
# )
# async def start_trial(
#     data: STrialActivate,
#     session: AsyncSession = Depends(get_session),
#     service: SubscriptionService = Depends(get_subscription_service),
#     user_auth: User = Depends(get_current_user),
# ) -> STrialActivateResponse:
#     """Активирует trial-подписку пользователя.
#
#     Args:
#         data: входные данные (tg_id, days)
#         session: DB session
#         service: business logic service
#         user_auth (User): Проверка,что пользователь зарегистрирован.
#
#     Returns
#         STrialActivateResponse: статус активации trial
#
#     Raises
#         ActiveSubscriptionExistsError
#         TrialAlreadyUsedError
#
#     """
#     await service.start_trial_subscription(
#         session=session,
#         tg_id=data.tg_id,
#         days=data.days,
#     )
#     return STrialActivateResponse(
#         status=TrialStatus.STARTED,
#     )
#
#
# @router.post(
#     "/activate",
#     response_model=SUserOut,
#     status_code=status.HTTP_200_OK,
#     summary="Активация платной подписки",
# )
# async def activate_subscription(
#     data: ActivateSubscriptionRequest,
#     session: AsyncSession = Depends(get_session),
#     service: SubscriptionService = Depends(get_subscription_service),
#     admin_auth: User = Depends(check_admin_role),
# ) -> SUserOut:
#     """Активирует или продлевает платную подписку пользователя.
#
#     Args:
#         data: запрос (tg_id, months, premium)
#         session: DB session
#         service: бизнес-логика подписок
#         admin_auth: Проверка, что пользователь админ.
#
#     Returns
#         SUserOut: обновлённый пользователь
#
#     """
#     return await service.activate_paid_subscription(
#         session=session,
#         user_id=data.tg_id,
#         months=data.months,
#         premium=data.premium,
#     )
#
#
# @router.get(
#     "/info",
#     response_model=SSubscriptionInfo,
#     summary="Информация о подписке и VPN конфигурациях",
# )
# async def get_subscription_info(
#     tg_id: int,
#     session: AsyncSession = Depends(get_session),
#     service: SubscriptionService = Depends(get_subscription_service),
#     user_auth: User = Depends(get_current_user),
# ) -> SSubscriptionInfo:
#     """Возвращает информацию о подписке и конфигурациях пользователя."""
#     return await service.get_subscription_info(
#         session=session,
#         tg_id=tg_id,
#     )
