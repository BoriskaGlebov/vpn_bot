from typing import Any

from starlette.requests import Request

from api.subscription.models import Subscription


class ActiveSubscriptionFilter:
    """Фильтр для отображения пользователей с активной подпиской."""

    title = "Активная подписка"
    parameter_name = "active_subscription"

    async def lookups(
        self, request: Request, model: Any, run_query: Any
    ) -> list[tuple[str, str]]:
        """Возвращает возможные значения фильтра и их человекочитаемые названия."""
        return [
            ("all", "Все"),
            ("yes", "Есть"),
            ("no", "Нет"),
        ]

    async def get_filtered_query(self, query: Any, value: str, model: Any) -> Any:
        """Возвращает SQLAlchemy-запрос, отфильтрованный по значению фильтра."""
        if value == "yes":
            return query.where(
                model.subscriptions.any(Subscription.is_active.is_(True))
            )
        elif value == "no":
            return query.where(
                ~model.subscriptions.any(Subscription.is_active.is_(True))
            )
        return query
