from typing import Any

from starlette.requests import Request

from api.payment.model import PaymentTransaction
from api.subscription.models import Subscription
from shared.enums.payment_enum import PaymentStatus


class SubscriptionSegmentFilter:
    """Фильтр пользователей по сегменту подписки (для сегментных рассылок, #385).

    Сегменты (решение заказчика — `no_active` включает `lapsed` как подмножество):
        - ``active``: есть активная подписка;
        - ``no_active``: нет активной подписки сейчас, независимо от истории
          платежей;
        - ``lapsed``: нет активной подписки, но был хотя бы один успешный
          платёж — узкий сегмент внутри ``no_active`` для рассылки
          «платил, но перестал».
    """

    title = "Сегмент подписки"
    parameter_name = "subscription_segment"

    async def lookups(
        self, request: Request, model: Any, run_query: Any
    ) -> list[tuple[str, str]]:
        """Возвращает возможные значения фильтра и их человекочитаемые названия."""
        return [
            ("all", "Все"),
            ("active", "Активная подписка"),
            ("no_active", "Без активной подписки"),
            ("lapsed", "Платил, но подписка закончилась"),
        ]

    async def get_filtered_query(self, query: Any, value: str, model: Any) -> Any:
        """Возвращает SQLAlchemy-запрос, отфильтрованный по сегменту подписки."""
        if value == "active":
            return query.where(
                model.subscriptions.any(Subscription.is_active.is_(True))
            )

        no_active = ~model.subscriptions.any(Subscription.is_active.is_(True))
        if value == "no_active":
            return query.where(no_active)

        if value == "lapsed":
            return query.where(
                no_active,
                model.payments.any(PaymentTransaction.status == PaymentStatus.PAID),
            )

        return query
