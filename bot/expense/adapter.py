from __future__ import annotations

import datetime

from loguru import logger

from bot.core.config import settings_bot
from bot.expense.schemas import SExpenseCreate, SExpenseRead, SYearlySummary
from bot.integrations.api_client import APIClient


class ExpenseAPIAdapter:
    """Адаптер для API расходов и финансовой аналитики."""

    def __init__(self, client: APIClient) -> None:
        """Инициализирует адаптер.

        Args:
            client: Экземпляр HTTP-клиента.

        """
        self._client = client

    async def get_yearly_summary(self, year: int | None = None) -> SYearlySummary:
        """Получает годовой финансовый итог.

        Args:
            year: Год (по умолчанию текущий).

        Returns
            SYearlySummary: Сводка за год.

        """
        if year is None:
            year = datetime.datetime.now(settings_bot.core.tzinfo).year
        logger.debug("Запрос финансового итога за {} год", year)
        data, _ = await self._client.get("/finance/summary", params={"year": year})
        return SYearlySummary.model_validate(data)

    async def create_expense(self, payload: SExpenseCreate) -> SExpenseRead:
        """Создаёт запись о расходе.

        Args:
            payload: Данные нового расхода.

        Returns
            SExpenseRead: Созданная запись.

        """
        logger.info(
            "Создание расхода: {} ₽ / {} / {}",
            payload.amount,
            payload.category,
            payload.node_name or "без ноды",
        )
        data, _ = await self._client.post(
            "/expenses",
            json=payload.model_dump(mode="json"),
        )
        return SExpenseRead.model_validate(data)
