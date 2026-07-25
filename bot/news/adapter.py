from loguru import logger

from bot.app_error.base_error import AppError
from bot.integrations.api_client import APIClient


class NewsAPIAdapter:
    """Адаптер для работы с API новостной рассылки.

    Инкапсулирует HTTP-взаимодействие с backend API
    и предоставляет удобные методы для получения данных.

    Args:
        client (APIClient): HTTP клиент для выполнения запросов.

    """

    def __init__(self, client: APIClient) -> None:
        self.client = client

    async def get_recipients(self) -> list[int]:
        """Получает список Telegram ID для рассылки.

        Returns
            list[int]: Список Telegram ID пользователей.

        Raises
            APIClientError: Если API вернул некорректный ответ.

        """
        data = await self.client.get("/news/recipients")

        if not isinstance(data, list):
            logger.error(
                "Некорректный формат ответа /news/recipients: {}",
                data,
            )
            raise AppError(
                message="Некорректный формат ответа API",
                details={
                    "expectation": "Ожидается список пользователей, но он не пришел."
                },
            )

        try:
            recipients = [int(user_id) for user_id in data]
        except (TypeError, ValueError) as exc:
            logger.error("Ошибка приведения ID: {}", data)
            raise AppError(message="Некорректные данные пользователей") from exc

        logger.info("Получено {} получателей рассылки", len(recipients))

        return recipients
