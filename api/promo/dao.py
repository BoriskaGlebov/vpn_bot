from loguru import logger
from sqlalchemy import or_
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.dao.base import BaseDAO
from api.promo.models import PromoCode, PromoCodeUsage


class PromoCodeDAO(BaseDAO[PromoCode]):
    """DAO для работы с промокодами."""

    model = PromoCode

    @classmethod
    async def try_increment_usage(
        cls, session: AsyncSession, promo_code_id: int
    ) -> bool:
        """Атомарно увеличивает счётчик применений, не превышая лимит.

        Условие лимита (`used_count < max_uses` либо `max_uses IS NULL`) не
        выразить через равенство — `BaseDAO._build_filters` строит только
        `AND(col == value, ...)`, поэтому для безопасного инкремента нужен
        отдельный `UPDATE ... WHERE ...`, выполняемый одним запросом к БД:
        два параллельных подтверждения оплаты с кодом, у которого
        `max_uses=1`, не должны оба увидеть "лимит не достигнут" и оба
        увеличить счётчик — тогда он останется атомарным и для случая,
        когда проверка и обновление разнесены в Python.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            promo_code_id: ID промокода.

        Returns
            bool: True, если лимит позволил увеличить счётчик (или лимита
            нет), False — если лимит уже достигнут.

        """
        stmt = (
            sqlalchemy_update(cls.model)
            .where(
                cls.model.id == promo_code_id,
                or_(
                    cls.model.max_uses.is_(None),
                    cls.model.used_count < cls.model.max_uses,
                ),
            )
            .values(used_count=cls.model.used_count + 1)
            .execution_options(synchronize_session="fetch")
        )
        result = await session.execute(stmt)
        rowcount: int = getattr(result, "rowcount", 0) or 0
        logger.info(
            "[DAO] Инкремент used_count промокода id={}: {}",
            promo_code_id,
            "успешно" if rowcount else "лимит достигнут",
        )
        return rowcount > 0


class PromoCodeUsageDAO(BaseDAO[PromoCodeUsage]):
    """DAO для работы с применениями промокодов."""

    model = PromoCodeUsage
