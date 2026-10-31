from datetime import datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings_api
from api.core.dao.base import BaseDAO
from api.payment.model import PaymentTransaction
from shared.enums.payment_enum import PaymentStatus


class PaymentTransactionDAO(BaseDAO[PaymentTransaction]):
    """DAO для работы с платежными транзакциями.

    Предоставляет методы для получения и агрегации
    информации о платежах пользователей.
    """

    model = PaymentTransaction

    @classmethod
    async def get_year_income(
        cls,
        session: AsyncSession,
        year: int | None = None,
    ) -> int:
        """Возвращает суммарный доход за указанный год.

        Учитываются только успешно оплаченные транзакции
        со статусом ``PAID``.

        Args:
            session:
                Асинхронная SQLAlchemy-сессия.

            year:
                Год для расчета дохода.
                Если не указан — используется текущий год в таймзоне
                проекта (`settings_api.core.timezone`).

        Returns
            Суммарный доход за год в минимальных единицах валюты.

        """
        tz = settings_api.core.tzinfo
        if year is None:
            year = datetime.now(tz=tz).year
        logger.info(
            f"[DAO] Расчет годового дохода для {cls.model.__name__}. Год: {year}"
        )
        # Границы года в таймзоне проекта, а не наивные — paid_at хранится
        # как timestamptz, и наивная граница сравнивалась бы по TimeZone
        # сессии Postgres, а не по явной зоне проекта.
        start = datetime(year, 1, 1, tzinfo=tz)
        end = datetime(year + 1, 1, 1, tzinfo=tz)

        stmt = select(func.coalesce(func.sum(cls.model.amount), 0)).where(
            cls.model.status == PaymentStatus.PAID,
            cls.model.paid_at >= start,
            cls.model.paid_at < end,
        )

        result = await session.execute(stmt)

        income: int = result.scalar_one()

        logger.info(
            f"[DAO] Годовой доход для {cls.model.__name__} за {year} год: {income}"
        )

        return income

    @classmethod
    async def get_monthly_revenue(
        cls,
        session: AsyncSession,
        year: int,
    ) -> list[tuple[str, int]]:
        """Возвращает суммарную выручку по месяцам за указанный год.

        Учитываются только транзакции со статусом PAID.
        Месяц определяется по полю `paid_at` в таймзоне проекта.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год агрегации.

        Returns
            list[tuple[str, int]]: Список пар (месяц 'YYYY-MM', выручка в руб),
            отсортированных по месяцу.

        """
        tz = settings_api.core.tzinfo
        start = datetime(year, 1, 1, tzinfo=tz)
        end = datetime(year + 1, 1, 1, tzinfo=tz)

        month_expr = func.to_char(
            func.timezone(settings_api.core.timezone, cls.model.paid_at),
            "YYYY-MM",
        )
        stmt = (
            select(
                month_expr.label("month"),
                func.sum(cls.model.amount).label("total"),
            )
            .where(
                cls.model.status == PaymentStatus.PAID,
                cls.model.paid_at >= start,
                cls.model.paid_at < end,
            )
            .group_by(month_expr)
            .order_by(month_expr)
        )
        result = await session.execute(stmt)
        return [(row.month, int(row.total)) for row in result.all()]

    @classmethod
    async def count_paying_users(
        cls,
        session: AsyncSession,
        year: int,
    ) -> int:
        """Возвращает количество уникальных плательщиков за год.

        Считает DISTINCT user_id из PAID-транзакций.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год.

        Returns
            int: Кол-во уникальных user_id.

        """
        tz = settings_api.core.tzinfo
        start = datetime(year, 1, 1, tzinfo=tz)
        end = datetime(year + 1, 1, 1, tzinfo=tz)

        stmt = select(
            func.coalesce(func.count(func.distinct(cls.model.user_id)), 0)
        ).where(
            cls.model.status == PaymentStatus.PAID,
            cls.model.paid_at >= start,
            cls.model.paid_at < end,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())

    @classmethod
    async def count_monthly_payments(
        cls,
        session: AsyncSession,
        year: int,
        month: int,
    ) -> int:
        """Возвращает количество PAID-транзакций за конкретный месяц.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год.
            month: Номер месяца (1-12).

        Returns
            int: Количество платежей.

        """
        tz = settings_api.core.tzinfo
        start = datetime(year, month, 1, tzinfo=tz)
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=tz)
        else:
            end = datetime(year, month + 1, 1, tzinfo=tz)

        stmt = select(func.count()).where(
            cls.model.status == PaymentStatus.PAID,
            cls.model.paid_at >= start,
            cls.model.paid_at < end,
        )
        result = await session.execute(stmt)
        return int(result.scalar_one())
