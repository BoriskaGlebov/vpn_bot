from datetime import date

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.dao.base import BaseDAO
from api.expense.models import Expense


class ExpenseDAO(BaseDAO[Expense]):
    """DAO для работы с расходами."""

    model = Expense

    @classmethod
    async def get_by_period(
        cls,
        session: AsyncSession,
        start: date,
        end: date,
    ) -> list[Expense]:
        """Возвращает расходы, чей период начала попадает в указанный диапазон.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            start: Начало диапазона (включительно).
            end: Конец диапазона (включительно).

        Returns
            list[Expense]: Список расходов, отсортированных по убыванию
            даты начала периода.

        """
        query = (
            select(cls.model)
            .where(
                cls.model.period_start >= start,
                cls.model.period_start <= end,
            )
            .order_by(cls.model.period_start.desc())
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def get_monthly_totals(
        cls,
        session: AsyncSession,
        year: int,
    ) -> list[tuple[str, int]]:
        """Возвращает суммарные расходы по месяцам за указанный год.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год, за который нужна агрегация.

        Returns
            list[tuple[str, int]]: Список пар (месяц в формате 'YYYY-MM',
            суммарный расход в рублях), отсортированных по месяцу по возрастанию.

        """
        # literal_column инлайнит формат в SQL без параметризации —
        # asyncpg иначе присваивает 'YYYY-MM' разные индексы ($1/$3),
        # и PostgreSQL не может сопоставить GROUP BY с SELECT.
        query = (
            select(
                func.to_char(cls.model.period_start, literal_column("'YYYY-MM'")).label(
                    "month"
                ),
                func.sum(cls.model.amount).label("total"),
            )
            .where(func.extract("year", cls.model.period_start) == year)
            .group_by(func.to_char(cls.model.period_start, literal_column("'YYYY-MM'")))
            .order_by(func.to_char(cls.model.period_start, literal_column("'YYYY-MM'")))
        )
        result = await session.execute(query)
        return [(row.month, int(row.total)) for row in result.all()]

    @classmethod
    async def get_yearly_by_category(
        cls,
        session: AsyncSession,
        year: int,
    ) -> list[tuple[str, int]]:
        """Возвращает суммарные расходы по категориям за год.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год агрегации.

        Returns
            list[tuple[str, int]]: Список пар (значение категории, сумма в рублях),
            отсортированных по убыванию суммы.

        """
        query = (
            select(
                cls.model.category,
                func.sum(cls.model.amount).label("total"),
            )
            .where(func.extract("year", cls.model.period_start) == year)
            .group_by(cls.model.category)
            .order_by(func.sum(cls.model.amount).desc())
        )
        result = await session.execute(query)
        return [(row[0].value, int(row[1])) for row in result.all()]
