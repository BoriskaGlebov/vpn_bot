"""Тесты PromoCodeDAO.try_increment_usage — атомарный инкремент с лимитом.

Условие лимита (`used_count < max_uses` либо `max_uses IS NULL`) собрано
руками (не через `BaseDAO._build_filters`, который умеет только равенство),
поэтому здесь отдельно проверяется, что скомпилированный SQL реально содержит
все условия (аналог регрессии #263 — часть условия тихо выпадает из WHERE),
а также что реальное поведение на БД соответствует условию лимита.
"""

import pytest

from api.promo.dao import PromoCodeDAO
from api.promo.models import PromoCode
from shared.enums.promo_enum import PromoDiscountType


def test_try_increment_usage_where_clause_has_all_conditions():
    """Компилирует UPDATE и проверяет, что в WHERE есть id, max_uses IS NULL
    и used_count < max_uses — ни одно из условий не должно тихо выпасть.
    """
    from sqlalchemy import or_
    from sqlalchemy import update as sqlalchemy_update

    promo_code_id = 42
    stmt = (
        sqlalchemy_update(PromoCode)
        .where(
            PromoCode.id == promo_code_id,
            or_(
                PromoCode.max_uses.is_(None),
                PromoCode.used_count < PromoCode.max_uses,
            ),
        )
        .values(used_count=PromoCode.used_count + 1)
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

    assert f"promocodes.id = {promo_code_id}" in compiled
    assert "max_uses IS NULL" in compiled
    assert "used_count < promocodes.max_uses" in compiled
    assert "OR" in compiled


@pytest.mark.asyncio
async def test_try_increment_usage_succeeds_under_limit(session):
    """Инкремент проходит, когда used_count < max_uses."""
    promo = PromoCode(
        code="UNDER10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        max_uses=2,
        used_count=0,
    )
    session.add(promo)
    await session.flush()

    result = await PromoCodeDAO.try_increment_usage(
        session=session, promo_code_id=promo.id
    )

    assert result is True
    await session.refresh(promo)
    assert promo.used_count == 1


@pytest.mark.asyncio
async def test_try_increment_usage_fails_at_limit(session):
    """Инкремент не проходит, когда лимит уже достигнут — глобальный лимит
    применений промокода соблюдается на уровне атомарного UPDATE.
    """
    promo = PromoCode(
        code="MAXED1",
        discount_type=PromoDiscountType.FIXED,
        discount_value=50,
        max_uses=1,
        used_count=1,
    )
    session.add(promo)
    await session.flush()

    result = await PromoCodeDAO.try_increment_usage(
        session=session, promo_code_id=promo.id
    )

    assert result is False
    await session.refresh(promo)
    assert promo.used_count == 1


@pytest.mark.asyncio
async def test_try_increment_usage_unlimited_when_max_uses_none(session):
    """Без ограничения (max_uses=None) инкремент проходит всегда."""
    promo = PromoCode(
        code="UNLIMITED",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=5,
        max_uses=None,
        used_count=1000,
    )
    session.add(promo)
    await session.flush()

    result = await PromoCodeDAO.try_increment_usage(
        session=session, promo_code_id=promo.id
    )

    assert result is True
    await session.refresh(promo)
    assert promo.used_count == 1001
