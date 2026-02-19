from typing import Any

from starlette.requests import Request

from bot.subscription.models import Subscription


class ActiveSubscriptionFilter:
    """Фильтр для отображения пользователей с активной подпиской.

    Этот фильтр используется в админке для фильтрации пользователей по наличию
    активной подписки.

    Attributes
        title (str): Читаемое название фильтра, отображаемое в админке.
        parameter_name (str): Имя параметра фильтра в URL-запросе.

    """

    title = "Активная подписка"
    parameter_name = "active_subscription"

    async def lookups(
        self, request: Request, model: Any, run_query: Any
    ) -> list[tuple[str, str]]:
        """Возвращает возможные значения фильтра и их человекочитаемые названия.

        Args
            request (Request): HTTP-запрос Starlette/FastAPI.
            model (Any): Модель SQLAlchemy, к которой применяется фильтр.
            run_query (Any): Функция для выполнения запроса (не используется здесь).

        Returns
            List[Tuple[str, str]]: Список пар (значение фильтра, название для отображения).

        """
        return [
            ("all", "Все"),
            ("yes", "Есть"),
            ("no", "Нет"),
        ]

    async def get_filtered_query(self, query: Any, value: str, model: Any) -> Any:
        """Возвращает SQLAlchemy-запрос, отфильтрованный по значению фильтра.

        Args:
            query (Any): SQLAlchemy Select или Query объект.
            value (str): Значение фильтра ('all', 'yes', 'no').
            model (Any): Модель SQLAlchemy, к которой применяется фильтр.

        Returns
            Any: Отфильтрованный SQLAlchemy Select/Query объект.

        """
        if value == "yes":
            return query.where(
                model.subscriptions.any(Subscription.is_active.is_(True))
            )
        elif value == "no":
            return query.where(
                ~model.subscriptions.any(Subscription.is_active.is_(True))
            )
        return query
