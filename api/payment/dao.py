from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.dao.base import BaseDAO
from api.payment.model import PaymentStatus, PaymentTransaction


# TODO документация типы данных и тесты если будут методы
class PaymentTransactionDAO(BaseDAO[PaymentTransaction]):
    """DAO для работы с платежными транзакциями.

    Предоставляет методы для получения и агрегации
    информации о платежах пользователей.
    """

    model = PaymentTransaction

    # TODO вернет то скорее DECIMAL???
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
                Если не указан — используется текущий год.

        Returns
            Суммарный доход за год в минимальных единицах валюты.

        """
        if year is None:
            year = datetime.now(tz=UTC).year
        logger.info(
            f"[DAO] Расчет годового дохода для {cls.model.__name__}. Год: {year}"
        )
        start = datetime(year, 1, 1)
        end = datetime(year + 1, 1, 1)

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
