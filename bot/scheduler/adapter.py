from bot.integrations.api_client import APIClient
from bot.scheduler.schemas import CheckAllSubscriptionsResponse

HTTPStatus = int


class SchedulerAPIAdapter:
    """Адаптер для взаимодействия с SubscriptionScheduler API.

    Инкапсулирует HTTP-вызовы эндпоинта планировщика `/scheduler/check-all`
    и преобразует JSON-ответы в Pydantic-схему `CheckAllSubscriptionsResponse`.

    Args:
        client: Асинхронный HTTP-клиент для выполнения запросов.

    """

    def __init__(self, client: APIClient) -> None:
        self._client = client

    async def check_all(self) -> CheckAllSubscriptionsResponse:
        """Запускает проверку всех пользователей и их подписок.

        Производит вызов эндпоинта `/scheduler/check-all`, который:
        - деактивирует истёкшие подписки
        - удаляет VPN-конфигурации при превышении лимитов
        - формирует список событий для дальнейшей обработки

        Returns
            CheckAllSubscriptionsResponse:объект с агрегированной статистикой и событиями

        Raises
            APIClientError: при некорректном ответе API.
            APIClientConnectionError: при проблемах соединения с API.

        """
        data, _ = await self._client.post("/scheduler/check-all")
        response = CheckAllSubscriptionsResponse.model_validate(data)
        return response
