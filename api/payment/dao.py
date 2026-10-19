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
