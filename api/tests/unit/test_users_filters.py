"""Сегментный фильтр подписки в UserAdmin (#385).

Условия проверяются компиляцией итогового SQL, а не чтением кода реализации
фильтра — `BaseDAO` уже один раз незаметно терял условия `WHERE` (#263).
"""

import pytest
from sqlalchemy import select

from api.users.filters import SubscriptionSegmentFilter
from api.users.models import User


def compile_sql(stmt: object) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]


@pytest.fixture
def filt() -> SubscriptionSegmentFilter:
    return SubscriptionSegmentFilter()


@pytest.mark.asyncio
async def test_active_filters_by_active_subscription(filt):
    query = await filt.get_filtered_query(select(User), "active", User)
    sql = compile_sql(query)

    assert "EXISTS" in sql
    assert "subscriptions" in sql
    assert "is_active IS true" in sql
    assert "NOT" not in sql


@pytest.mark.asyncio
async def test_no_active_excludes_users_with_active_subscription(filt):
    query = await filt.get_filtered_query(select(User), "no_active", User)
    sql = compile_sql(query)

    assert "NOT (EXISTS" in sql
    assert "subscriptions" in sql
    assert "is_active IS true" in sql
    assert "paymenttransactions" not in sql


@pytest.mark.asyncio
async def test_lapsed_requires_no_active_subscription_and_paid_transaction(filt):
    """lapsed = нет активной подписки И есть успешный (PAID) платёж — оба условия
    обязаны присутствовать в скомпилированном запросе одновременно.
    """
    query = await filt.get_filtered_query(select(User), "lapsed", User)
    sql = compile_sql(query)

    assert "NOT (EXISTS" in sql
    assert "subscriptions" in sql
    assert "is_active IS true" in sql
    assert "paymenttransactions" in sql
    assert "status = 'PAID'" in sql


@pytest.mark.asyncio
async def test_all_returns_query_unchanged(filt):
    query = select(User)
    filtered = await filt.get_filtered_query(query, "all", User)

    assert filtered is query


@pytest.mark.asyncio
async def test_lookups_expose_three_segments(filt):
    values = [
        value
        for value, _ in await filt.lookups(request=None, model=User, run_query=None)
    ]

    assert values == ["all", "active", "no_active", "lapsed"]
