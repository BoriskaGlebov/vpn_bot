from typing import Optional

import pytest
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from bot.dao.base import BaseDAO
from bot.database import Base


class TmpModel(Base):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[Optional[int]] = mapped_column(nullable=True)


class TmpSchema(BaseModel):
    id: Optional[int] = None
    name: str
    value: Optional[int] = None


class FilterSchema(BaseModel):
    name: Optional[str] = None
    value: Optional[int] = None


class TmpDAO(BaseDAO[TmpModel]):
    model = TmpModel


@pytest.fixture(autouse=True)
async def setup_test_table(session: AsyncSession):
    """Создаёт таблицу test_models перед каждым тестом и удаляет после."""
    async with session.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.mark.asyncio
@pytest.mark.dao
async def test_add_and_find_by_id(session):
    item = await TmpDAO.add(session, TmpSchema(name="item1", value=10))

    found = await TmpDAO.find_one_or_none_by_id(item.id, session)
    assert found is not None
    assert found.name == "item1"
    assert found.value == 10


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_one_or_none(session):
    await TmpDAO.add(session, TmpSchema(name="unique", value=5))

    found = await TmpDAO.find_one_or_none(session, FilterSchema(name="unique"))
    assert found is not None
    assert found.value == 5


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_all_with_filters(session):
    await TmpDAO.add(session, TmpSchema(name="a", value=1))
    await TmpDAO.add(session, TmpSchema(name="a", value=2))
    await TmpDAO.add(session, TmpSchema(name="b", value=3))

    records = await TmpDAO.find_all(session, FilterSchema(name="a"))
    assert len(records) == 2
    assert all(r.name == "a" for r in records)


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_all_without_filters(session):
    await TmpDAO.add(session, TmpSchema(name="x"))
    await TmpDAO.add(session, TmpSchema(name="y"))

    all_records = await TmpDAO.find_all(session)
    assert len(all_records) >= 2


@pytest.mark.asyncio
@pytest.mark.dao
async def test_update_records(session):
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="to_update", value=1))
    await dao.update(
        session,
        filters=FilterSchema(name="to_update"),
        values=TmpSchema(name="to_update", value=99),
    )

    found = await dao.find_one_or_none(session, FilterSchema(name="to_update"))
    assert found.value == 99


@pytest.mark.asyncio
@pytest.mark.dao
async def test_delete_records(session):
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="to_delete"))

    deleted = await dao.delete(session, FilterSchema(name="to_delete"))
    assert deleted == 1

    result = await dao.find_one_or_none(session, FilterSchema(name="to_delete"))
    assert result is None


@pytest.mark.asyncio
@pytest.mark.dao
async def test_count_records(session):
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="c1"))
    await dao.add(session, TmpSchema(name="c2"))

    count = await dao.count(session, FilterSchema())
    assert count >= 2


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_by_ids(session):
    dao = TmpDAO()
    i1 = await dao.add(session, TmpSchema(name="one"))
    i2 = await dao.add(session, TmpSchema(name="two"))

    found = await dao.find_by_ids(session, [i1.id, i2.id])
    assert {r.name for r in found} == {"one", "two"}


@pytest.mark.asyncio
@pytest.mark.dao
async def test_upsert_creates_and_updates(session):
    dao = TmpDAO()

    created = await dao.upsert(
        session,
        [
            "name",
        ],
        TmpSchema(name="upserted", value=1),
    )
    assert created.value == 1

    updated = await dao.upsert(
        session,
        [
            "name",
        ],
        TmpSchema(name="upserted", value=2),
    )
    assert updated.value == 2


@pytest.mark.asyncio
@pytest.mark.dao
async def test_bulk_update(session):
    dao = TmpDAO()
    item1 = await dao.add(session, TmpSchema(name="bulk1", value=1))
    item2 = await dao.add(session, TmpSchema(name="bulk2", value=1))

    count = await dao.bulk_update(
        session,
        [
            TmpSchema(name="bulk1", value=10, id=item1.id),
            TmpSchema(name="bulk2", value=20, id=item2.id),
        ],
    )

    assert count == 2
    all_records = await dao.find_all(session)
    assert {r.value for r in all_records} >= {10, 20}
