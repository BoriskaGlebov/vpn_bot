from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_current_user, get_session
from api.payment.dependencies import get_payment_service
from api.payment.model import PaymentSource
from api.payment.schemas import (
    SAttachProviderPayment,
    SConfirmPaymentResponse,
    SCreateManualPaymentTransaction,
    SPaymentTransactionResponse,
    STransactionIDFilter,
)
from api.payment.services import PaymentService
from api.users.models import User

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
    service: PaymentService = Depends(get_payment_service),
    user_auth: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:
    """Создаёт новую платежную транзакцию.

    Endpoint используется для создания платежа текущим авторизованным пользователем.

    Args:
        transaction: Данные создаваемой платежной транзакции.
        service: Сервис бизнес-логики платежей.
        user_auth: Авторизованный пользователь.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SPaymentTransactionResponse: Созданная платежная транзакция.

    """
    res = await service.create_transaction(
        session=session, transaction=transaction, user_auth=user_auth
    )
    return res


@router.get(
    "/transaction",
    response_model=SPaymentTransactionResponse,
    summary="Получение транзакции по gateway ID",
    description=(
        "Возвращает платежную транзакцию по идентификатору платёжного шлюза "
        "(gateway_transaction_id). Используется для синхронизации статусов "
        "платежей с внешними провайдерами."
    ),
    response_description="Найденная платежная транзакция.",
)
async def get_by_gateway_id(
    gateway_transaction_id: str,
    service: PaymentService = Depends(get_payment_service),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:
    """Получение платежной транзакции по идентификатору платежного шлюза.

    Выполняет поиск транзакции в базе данных по `gateway_transaction_id`,
    который был получен от внешнего платежного провайдера (например, Stripe,
    YooKassa и др.).

    Args:
        gateway_transaction_id:
            Уникальный идентификатор транзакции в платежном шлюзе.
            Используется для поиска и синхронизации статуса платежа.

        service:
            Сервис, содержащий бизнес-логику работы с платежами.

        session:
            Асинхронная SQLAlchemy-сессия для доступа к базе данных.

    Returns
        SPaymentTransactionResponse:
            Объект платежной транзакции, если найден.

    Raises
        HTTPException:
            404 — если транзакция с указанным gateway_transaction_id не найдена.

    """
    return await service.get_by_gateway_id(
        session=session,
        gateway_transaction_id=gateway_transaction_id,
    )


@router.post(
    "/transaction/{transaction_id}/provider",
    response_model=SPaymentTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Привязка платежного провайдера к транзакции",
    description=(
        "Привязывает внешнего платёжного провайдера (gateway/provider) к "
        "существующей платежной транзакции. Используется для фиксации "
        "идентификатора транзакции во внешней платёжной системе и "
        "синхронизации статусов оплаты."
    ),
    response_description="Обновлённая платежная транзакция с привязанным провайдером.",
)
async def attach_provider_payment(
    transaction_id: UUID,
    payload: SAttachProviderPayment,
    service: PaymentService = Depends(get_payment_service),
    session: AsyncSession = Depends(get_session),
    user_auth: User = Depends(get_current_user),
) -> SPaymentTransactionResponse:
    """Привязка платежного провайдера к существующей транзакции.

    Выполняет связывание внутренней платежной транзакции с внешним
    платёжным провайдером (gateway/provider), используя идентификатор
    транзакции во внешней системе.

    Этот endpoint используется после создания платежа, когда внешний
    провайдер возвращает `gateway_transaction_id`, который необходимо
    сохранить для дальнейшей синхронизации статусов оплаты.

    Args:
        transaction_id:
            Внутренний UUID платежной транзакции в системе.

        payload:
            Данные внешнего платёжного провайдера, включая
            `gateway_transaction_id` и связанные параметры.

        service:
            Сервис бизнес-логики платежей.

        session:
            Асинхронная SQLAlchemy-сессия.

        user_auth:
            Текущий авторизованный пользователь (используется для
            проверки прав доступа и безопасности операции).

    Returns
        SPaymentTransactionResponse:
            Обновлённая платежная транзакция с привязанным provider/gateway.

    Raises
        PaymentTransactionNotFoundError: Если транзакция не найдена.

    """
    return await service.attach_provider_payment(
        session=session, transaction_id=transaction_id, gateway_info=payload
    )


@router.post(
    "/transaction/{transaction_id}/paid",
    response_model=SPaymentTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Отметка начала обработки платежа",
    description="Фиксирует начало обработки платежа по транзакции.",
)
async def mark_payment_started(
    transaction_id: UUID,
    service: PaymentService = Depends(get_payment_service),
    session: AsyncSession = Depends(get_session),
    user_auth: User = Depends(get_current_user),
) -> SPaymentTransactionResponse:
    """Фиксирует начало обработки платежа.

    Помечает транзакцию как находящуюся в процессе оплаты.

    Args:
        transaction_id: UUID транзакции.
        service: Сервис платежей.
        session: Асинхронная SQLAlchemy-сессия.
        user_auth: Авторизованный пользователь.

    Returns
        SPaymentTransactionResponse: Обновлённая транзакция.

    """
    return await service.mark_payment_started(
        session=session,
        transaction_id=transaction_id,
    )


@router.post(
    "/transaction/admin/confirm",
    response_model=SConfirmPaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Подтверждение платежа администратором",
    description=(
        "Подтверждает платежную транзакцию, активирует подписку пользователя "
        "и начисляет реферальный бонус при наличии реферальной связи."
    ),
    response_description="Результат обработки платежа, подписки и реферального бонуса.",
)
async def admin_confirm_transaction(
    data: STransactionIDFilter,
    service: PaymentService = Depends(get_payment_service),
    admin_auth: User = Depends(check_admin_role),
    session: AsyncSession = Depends(get_session),
) -> SConfirmPaymentResponse:
    """Подтверждает платеж администратором.

    После успешного подтверждения выполняется:
        - перевод транзакции в статус PAID;
        - активация подписки пользователя;
        - начисление реферального бонуса (если применимо).

    Args:
        data: Данные транзакции.
        service: Сервис платежей.
        admin_auth: Авторизованный администратор.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SConfirmPaymentResponse: Результат подтверждения платежа.

    """
    return await service.confirm_payment_flow(
        session=session,
        data=data,
        payment_source=PaymentSource.MANUAL,
        admin_id=admin_auth.id,
    )


@router.post(
    "/transaction/webhook/confirm",
    response_model=SConfirmPaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Подтверждение платежа через webhook",
    description=(
        "Подтверждает платежную транзакцию через webhook внешнего "
        "платёжного провайдера. После подтверждения автоматически "
        "активируется подписка пользователя и начисляется "
        "реферальный бонус при наличии реферальной связи."
    ),
    response_description=(
        "Результат подтверждения платежа, активации подписки "
        "и обработки реферального бонуса."
    ),
)
async def webhook_confirm_transaction(
    data: STransactionIDFilter,
    service: PaymentService = Depends(get_payment_service),
    session: AsyncSession = Depends(get_session),
) -> SConfirmPaymentResponse:
    """Подтверждает платежную транзакцию через webhook.

    Endpoint используется внешними платёжными провайдерами
    для уведомления системы об успешной оплате.

    После успешного подтверждения:
        - транзакция переводится в статус ``PAID``;
        - активируется подписка пользователя;
        - начисляется реферальный бонус (если применимо).

    Args:
        data:
            Данные подтверждаемой транзакции.

        service:
            Сервис бизнес-логики платежей.

        session:
            Асинхронная SQLAlchemy-сессия.

    Returns
        SConfirmPaymentResponse:
            Результат подтверждения платежа, активации подписки
            и обработки реферального бонуса.

    Raises
        PaymentTransactionNotFoundError:
            Если транзакция не найдена.

        PaymentAlreadyProcessedError:
            Если транзакция уже была обработана.

    """
    return await service.confirm_payment_flow(
        session=session,
        data=data,
        payment_source=PaymentSource.GATEWAY,
    )


@router.post(
    "/transaction/cancel",
    response_model=SPaymentTransactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Отмена платежной транзакции",
    description=("Отменяет платежную транзакцию и переводит её в статус ``CANCELED``."),
    response_description="Обновлённая платежная транзакция.",
)
async def cancel_transaction(
    data: STransactionIDFilter,
    service: PaymentService = Depends(get_payment_service),
    user_auth: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SPaymentTransactionResponse:
    """Отменяет платежную транзакцию.

    Endpoint используется для отмены платежной транзакции.
    После успешной обработки транзакция переводится
    в статус ``CANCELED``.

    Args:
        data:
            Данные отменяемой транзакции.

        service:
            Сервис бизнес-логики платежей.

        user_auth:
            Авторизованный пользователь.

        session:
            Асинхронная SQLAlchemy-сессия.

    Returns
        SPaymentTransactionResponse:
            Обновлённая платежная транзакция.

    Raises
        PaymentTransactionNotFoundError:
            Если транзакция не найдена.

        PaymentAlreadyProcessedError:
            Если транзакция уже была обработана.

    """
    cancel_data = data

    res = await service.cancel_transaction(
        session=session,
        data=cancel_data,
    )

    return res
