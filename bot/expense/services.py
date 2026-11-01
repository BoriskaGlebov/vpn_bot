from __future__ import annotations

from loguru import logger

from bot.expense.adapter import ExpenseAPIAdapter
from bot.expense.schemas import SExpenseCreate, SExpenseRead, SYearlySummary


class ExpenseService:
    """Бизнес-логика управления расходами в боте."""

    def __init__(self, adapter: ExpenseAPIAdapter) -> None:
        """Инициализирует сервис.

        Args:
            adapter: Адаптер для API расходов.

        """
        self.adapter = adapter

    async def get_yearly_summary(self, year: int | None = None) -> SYearlySummary:
        """Получает годовой финансовый итог.

        Args:
            year: Год (по умолчанию текущий).

        Returns
            SYearlySummary: Сводка за год.

        """
        summary = await self.adapter.get_yearly_summary(year=year)
        logger.debug("Годовой итог: profit={}", summary.total_profit)
        return summary

    async def create_expense(self, data: SExpenseCreate) -> SExpenseRead:
        """Создаёт расход через API.

        Args:
            data: Данные нового расхода.

        Returns
            SExpenseRead: Созданная запись.

        """
        result = await self.adapter.create_expense(data)
        logger.info("Расход создан: id={} amount={}", result.id, result.amount)
        return result
