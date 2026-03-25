from bot.news.adapter import NewsAPIAdapter


class NewsService:
    """Сервис для работы с новостной рассылкой через Telegram-бота.

    Attributes
        bot (Bot): Экземпляр бота Aiogram.
        logger (Logger): Логгер Loguru для записи информации и ошибок.

    """

    def __init__(self, adapter: NewsAPIAdapter) -> None:
        self.api_adapter = adapter

    async def all_users_id(self) -> list[int]:
        """Получает список Telegram ID всех пользователей, кроме администраторов.

        Returns
            List[int]: Список Telegram ID пользователей для рассылки.

        """
        return await self.api_adapter.get_recipients()
