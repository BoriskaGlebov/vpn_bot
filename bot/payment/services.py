from dataclasses import asdict
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from bot.notification.services import NotificationService
from bot.payment.adapter import PaymentAPIAdapter
from bot.payment.dto import (
    CreatedPaymentDTO,
    CreatePaymentDTO,
    PaymentStatus,
    PaymentWebhookDTO,
)
from bot.payment.providers.payment_client import BasePaymentProvider
from bot.payment.schemas import (
    SConfirmPaymentResponse,
    SCreatePayment,
    SPaymentTransactionResponse,
)
from bot.subscription.enums import ToggleSubscriptionMode

if TYPE_CHECKING:
    from subscription.services import SubscriptionService


# TODO  Новый класс не протестирован, нужно логирование, тесты
class PaymentService:
    """Сервис платежей — оркестрирует создание/подтверждение/отмену транзакций.

    Связывает внутренний Payment API (через `PaymentAPIAdapter`) с внешним
    платёжным шлюзом (через `BasePaymentProvider`).
    """

    def __init__(
        self, adapter: PaymentAPIAdapter, provider: BasePaymentProvider
    ) -> None:
        self.adapter = adapter
        self.provider = provider

    async def create_transaction(
        self, amount: int, subscription_months: int, is_premium: bool, is_founder: bool
    ) -> SCreatePayment:
        """Создаёт транзакцию во внутреннем API и платёж у провайдера.

        Args:
            amount: Сумма платежа в минимальных единицах.
            subscription_months: Количество месяцев подписки.
            is_premium: Флаг премиум-подписки.
            is_founder: Флаг пользователя-основателя.

        Returns
            SCreatePayment: Ссылка на оплату и данные созданной транзакции.

        """
        api_res = await self.adapter.create_transaction(
            amount=amount,
            subscription_months=subscription_months,
            is_premium=is_premium,
            is_founder=is_founder,
        )
        if is_premium:
            sub_type = ToggleSubscriptionMode.PREMIUM
        elif is_founder:
            sub_type = ToggleSubscriptionMode.FOUNDER
        else:
            sub_type = ToggleSubscriptionMode.STANDARD
        payment_data = CreatePaymentDTO(
            amount=Decimal(amount),
            currency="RUB",
            order_id=str(api_res.id),
            description=f"Оплата {sub_type.value} подписки на {subscription_months}мес.",
        )

        prov_res: CreatedPaymentDTO = await self.provider.create_payment(
            data=payment_data
        )
        tx_final = await self.adapter.attach_provider_payment(
            transaction_id=api_res.id,
            gateway_transaction_id=prov_res.provider_payment_id,
            gateway_payload=asdict(prov_res),
        )

        return SCreatePayment(
            payment_url=prov_res.payment_url,
            **tx_final.model_dump(),
        )

    async def cancel_transaction(
        self, transaction_id: UUID
    ) -> SPaymentTransactionResponse:
        """Отменяет платёжную транзакцию.

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Данные отменённой транзакции.

        """
        tx_res = await self.adapter.cancel_transaction(transaction_id=transaction_id)
        return tx_res

    async def confirm_transaction(
        self, transaction_id: UUID
    ) -> SConfirmPaymentResponse:
        """Подтверждает платёжную транзакцию (администратором).

        Args:
            transaction_id: UUID транзакции.

        Returns
            SConfirmPaymentResponse: Результат подтверждения.

        """
        tx_res = await self.adapter.confirm_transaction(transaction_id=transaction_id)
        return tx_res

    async def webhook_confirm_transaction(
        self, transaction_id: UUID
    ) -> SConfirmPaymentResponse:
        """Подтверждает платёжную транзакцию по вебхуку платёжного провайдера.

        Args:
            transaction_id: UUID транзакции.

        Returns
            SConfirmPaymentResponse: Результат подтверждения.

        """
        tx_res = await self.adapter.webhook_confirm_transaction(
            transaction_id=transaction_id
        )
        print(tx_res)
        return tx_res

    async def mark_payment_started(
        self, transaction_id: UUID
    ) -> SPaymentTransactionResponse:
        """Помечает транзакцию как оплаченную пользователем (ожидает подтверждения).

        Args:
            transaction_id: UUID транзакции.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        """
        tx_res = await self.adapter.mark_payment_started(transaction_id=transaction_id)

        return tx_res

    async def get_by_gateway_id(
        self, gateway_transaction_id: str
    ) -> SPaymentTransactionResponse:
        """Находит транзакцию по ID платежа во внешнем шлюзе.

        Args:
            gateway_transaction_id: ID транзакции внешнего платёжного шлюза.

        Returns
            SPaymentTransactionResponse: Найденная транзакция.

        """
        tx_res = await self.adapter.get_by_gateway_id(
            gateway_transaction_id=gateway_transaction_id
        )
        return tx_res


class PaymentWebhookService:
    """Обрабатывает входящие события вебхука платёжного провайдера."""

    def __init__(
        self,
        payment_service: PaymentService,
        subscription_service: "SubscriptionService",
        notification_service: NotificationService,
    ) -> None:
        self.payment_service = payment_service
        self.subscription_service = subscription_service
        self.notification_service = notification_service

    async def handle_event(self, event: PaymentWebhookDTO) -> None:
        """Обрабатывает событие вебхука и уведомляет пользователя о результате.

        Args:
            event: Данные события вебхука (статус платежа и ID транзакции).

        """
        tx = await self.payment_service.get_by_gateway_id(
            gateway_transaction_id=event.provider_payment_id
        )
        print("Информация по транзакции")
        print(tx)
        if event.status == PaymentStatus.PAID:
            # Через subscription_service, а не payment_service напрямую: она
            # после подтверждения транзакции и продления подписки в БД ещё
            # продлевает XRay-конфиги пользователя на панелях 3x-ui (см.
            # `SubscriptionService._extend_xray_after_payment`).
            await self.subscription_service.webhook_confirm_transaction(tx.id)

            await self.notification_service.notify_payment_success(
                user_id=tx.tg_id,
                amount=tx.amount,
            )

        elif event.status == PaymentStatus.FAILED:
            await self.payment_service.cancel_transaction(tx.id)

            await self.notification_service.notify_payment_failed(
                user_id=tx.tg_id,
            )
