"""Тесты BaseDAO (api/core/dao/base.py) на временной модели, не завязанные на реальную схему."""

from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from api.core.dao.base import BaseDAO
from api.core.database import Base


class TmpModel(Base):
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[int | None] = mapped_column(nullable=True)


class TmpSchema(BaseModel):
    id: int | None = None
    name: str
    value: int | None = None


class FilterSchema(BaseModel):
    name: str | None = None
    value: int | None = None


class TmpValuesSchema(BaseModel):
    """Схема значений для update() — без `id`, как во всех реальных вызовах в api/."""

    name: str | None = None
    value: int | None = None


class TmpValueDefaultSchema(BaseModel):
    """Схема значений с полем по умолчанию, которое не планируется передавать явно."""

    value: int = 0


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
    """add() создаёт запись, find_one_or_none_by_id() находит её по PK."""
    item = await TmpDAO.add(session, TmpSchema(name="item1", value=10))
    await session.flush()
    found = await TmpDAO.find_one_or_none_by_id(item.id, session)
    assert found is not None
    assert found.name == "item1"
    assert found.value == 10


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_one_or_none(session):
    """find_one_or_none() находит запись по произвольному фильтру."""
    await TmpDAO.add(session, TmpSchema(name="unique", value=5))

    found = await TmpDAO.find_one_or_none(session, FilterSchema(name="unique"))
    assert found is not None
    assert found.value == 5


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_all_with_filters(session):
    """find_all() с фильтром возвращает только подходящие записи."""
    await TmpDAO.add(session, TmpSchema(name="a", value=1))
    await TmpDAO.add(session, TmpSchema(name="a", value=2))
    await TmpDAO.add(session, TmpSchema(name="b", value=3))

    records = await TmpDAO.find_all(session, FilterSchema(name="a"))
    assert len(records) == 2
    assert all(r.name == "a" for r in records)


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_all_without_filters(session):
    """find_all() без фильтра возвращает все записи таблицы."""
    await TmpDAO.add(session, TmpSchema(name="x"))
    await TmpDAO.add(session, TmpSchema(name="y"))

    all_records = await TmpDAO.find_all(session)
    assert len(all_records) >= 2


@pytest.mark.asyncio
@pytest.mark.dao
async def test_update_records(session):
    """update() применяет values к записям, подходящим под filters."""
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="to_update", value=1))
    await dao.update(
        session,
        filters=FilterSchema(name="to_update"),
        values=TmpValuesSchema(name="to_update", value=99),
    )

    found = await dao.find_one_or_none(session, FilterSchema(name="to_update"))
    assert found.value == 99


@pytest.mark.asyncio
@pytest.mark.dao
async def test_crud_does_not_log_values_at_info_level(session, monkeypatch):
    """add/update/delete не пишут значения записей на INFO (#235).

    `logger_level_file` по умолчанию `INFO` — всё, что уходит на этот уровень,
    попадает в постоянный `file.log` с `retention=30 days`. Значения (которые
    могут быть telegram_id, username и т.п.) должны логироваться не выше DEBUG.
    """
    log_mock = MagicMock()
    monkeypatch.setattr("api.core.dao.base.logger", log_mock)
    marker = "should-not-reach-info-level"

    await TmpDAO.add(session, TmpSchema(name=marker, value=1))
    await TmpDAO.update(
        session,
        filters=FilterSchema(name=marker),
        values=TmpValuesSchema(name=marker, value=2),
    )
    await TmpDAO.delete(session, FilterSchema(name=marker))

    info_messages = [str(call.args[0]) for call in log_mock.info.call_args_list]
    debug_messages = [str(call.args[0]) for call in log_mock.debug.call_args_list]

    assert not any(marker in msg for msg in info_messages)
    assert any(marker in msg for msg in debug_messages)


@pytest.mark.asyncio
@pytest.mark.dao
async def test_add_many_assigns_ids(session):
    """add_many() делает flush — у возвращённых записей уже есть id."""
    dao = TmpDAO()
    records = await dao.add_many(
        session,
        [TmpSchema(name="m1"), TmpSchema(name="m2")],
    )

    assert all(r.id is not None for r in records)


@pytest.mark.asyncio
@pytest.mark.dao
async def test_add_many_integrity_error_raises_from_method(session):
    """Нарушение целостности (дублирующийся id) всплывает из add_many, а не при коммите."""
    dao = TmpDAO()
    existing = await dao.add(session, TmpSchema(name="first"))
    await session.flush()

    with pytest.raises(IntegrityError):
        await dao.add_many(session, [TmpSchema(id=existing.id, name="duplicate")])


@pytest.mark.asyncio
@pytest.mark.dao
async def test_update_values_includes_unset_default_fields(session):
    """update(values=...): поле со значением по умолчанию, не переданное явно,
    всё равно попадает в SET — в отличие от фильтров, значения не должны
    молча выпадать из UPDATE (#234).
    """
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="defaults", value=5))

    await dao.update(
        session,
        filters=FilterSchema(name="defaults"),
        values=TmpValueDefaultSchema(),  # value не передан явно, используется дефолт 0
    )

    found = await dao.find_one_or_none(session, FilterSchema(name="defaults"))
    assert found.value == 0


@pytest.mark.asyncio
@pytest.mark.dao
async def test_update_without_filter_raises(session):
    """update() с пустым фильтром отказывает, а не обновляет всю таблицу."""
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="untouched", value=1))

    with pytest.raises(ValueError, match="фильтр"):
        await dao.update(
            session,
            filters=FilterSchema(),
            values=TmpSchema(name="untouched", value=99),
        )

    found = await dao.find_one_or_none(session, FilterSchema(name="untouched"))
    assert found.value == 1


@pytest.mark.asyncio
@pytest.mark.dao
async def test_delete_records(session):
    """delete() удаляет подходящие записи и возвращает их количество."""
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="to_delete"))

    deleted = await dao.delete(session, FilterSchema(name="to_delete"))
    assert deleted == 1

    result = await dao.find_one_or_none(session, FilterSchema(name="to_delete"))
    assert result is None


@pytest.mark.asyncio
@pytest.mark.dao
async def test_count_records(session):
    """count() считает записи, подходящие под filters."""
    dao = TmpDAO()
    await dao.add(session, TmpSchema(name="c1"))
    await dao.add(session, TmpSchema(name="c2"))

    count = await dao.count(session, FilterSchema())
    assert count >= 2


@pytest.mark.asyncio
@pytest.mark.dao
async def test_find_by_ids(session):
    """find_by_ids() возвращает записи по списку первичных ключей."""
    dao = TmpDAO()
    i1 = await dao.add(session, TmpSchema(name="one"))
    i2 = await dao.add(session, TmpSchema(name="two"))
    await session.flush()
    found = await dao.find_by_ids(session, [i1.id, i2.id])
    assert {r.name for r in found} == {"one", "two"}
