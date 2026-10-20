from collections.abc import Sequence
from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)
from uuid import UUID

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, delete, func, select, true
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.interfaces import ORMOption

from api.core.database import Base
from api.core.database import redact as _redact_values

T = TypeVar("T", bound=Base)


class BaseDAO(Generic[T]):  # noqa: UP046
    """Общий класс для CRUD-операций с моделями через асинхронные сессии SQLAlchemy."""

    model: type[T]

    @staticmethod
    def _to_dict(filters: BaseModel | None) -> dict[str, Any]:
        """Преобразование схемы ФИЛЬТРА в словарь.

        `exclude_unset=True` — в фильтр/WHERE попадают только явно переданные
        поля. Это обязательное свойство для фильтров: непереданное поле не
        должно ограничивать выборку/изменяемый набор строк своим значением по
        умолчанию (иначе, например, `STransactionPendingFilter(id=...)` без
        явного `status=` тихо потерял бы часть условия `WHERE`).
        """
        return filters.model_dump(exclude_unset=True) if filters else {}

    @staticmethod
    def _values_to_dict(values: BaseModel | None) -> dict[str, Any]:
        """Преобразование схемы ЗНАЧЕНИЙ (для `UPDATE ... SET`) в словарь.

        `exclude_unset=False`, в отличие от `_to_dict`: поле со значением по
        умолчанию, не переданное явно в конструктор схемы, всё равно должно
        попасть в `SET` — иначе обновление тихо не затрагивает колонку, хотя
        вызывающий код по тексту схемы ожидает, что она запишется.
        """
        return values.model_dump(exclude_unset=False) if values else {}

    @staticmethod
    def _redact(values: dict[str, Any]) -> dict[str, Any]:
        """Маскирует потенциально чувствительные поля перед логированием.

        Например, `PaymentTransaction.gateway_payload` (сырые данные
        платёжного шлюза) иначе целиком попадал бы в `file.log`. Реализация
        общая с `Base.to_dict_redacted` (см. `api.core.database.redact`) —
        чтобы маскирование не обходилось через `__repr__`/`to_dict` модели.

        Args:
            values: Словарь значений записи.

        Returns
            dict[str, Any]: Копия словаря; значения ключей, содержащих
                чувствительные подстроки, заменены на `"***"`.

        """
        return _redact_values(values)

    @classmethod
    def _build_filters(cls, f: dict[str, Any]) -> ColumnElement[bool]:
        filters = [getattr(cls.model, k) == v for k, v in f.items()]
        return and_(*filters) if filters else true()

    @classmethod
    async def find_one_or_none_by_id(
        cls, data_id: int | UUID, session: AsyncSession
    ) -> T | None:
        """Находит запись по ID."""
        logger.debug(f"[DAO] Поиск {cls.model.__name__} с ID: {data_id}")

        query = select(cls.model).where(cls.model.id == data_id)

        result = await session.execute(query)
        record = cast(T | None, result.scalar_one_or_none())  # type: ignore[redundant-cast]
        logger.debug(
            f"[DAO] Результат поиска {cls.model.__name__} id={data_id}: "
            f"{'найдена id=' + str(record.id) if record else 'не найдена'}"
        )
        return record

    @classmethod
    async def find_one_or_none(
        cls,
        session: AsyncSession,
        filters: BaseModel,
        options: Sequence[ORMOption] | None = None,
    ) -> T | None:
        """Находит одну запись по фильтрам."""
        filter_dict = cls._to_dict(filters=filters)
        logger.debug(
            f"[DAO] Поиск одной записи {cls.model.__name__} по фильтрам: "
            f"{cls._redact(filter_dict)}"
        )

        filters_clause = cls._build_filters(filter_dict)
        query = select(cls.model).where(filters_clause)
        if options:
            for option in options:
                query = query.options(option)
        result = await session.execute(query)
        record = cast(T | None, result.scalar_one_or_none())  # type: ignore[redundant-cast]
        logger.debug(
            f"[DAO] {cls.model.__name__}: "
            f"{'найдена id=' + str(record.id) if record else 'не найдена'}"
        )
        return record

    @classmethod
    async def find_all(
        cls,
        session: AsyncSession,
        filters: BaseModel | None = None,
        options: Sequence[ORMOption] | None = None,
    ) -> list[T]:
        """Находит все записи по фильтрам."""
        filter_dict = cls._to_dict(filters=filters)
        logger.debug(
            f"[DAO] Поиск всех записей {cls.model.__name__} по фильтрам: "
            f"{cls._redact(filter_dict)}"
        )

        filters_clause = cls._build_filters(filter_dict)
        query = select(cls.model).where(filters_clause)
        if options:
            for option in options:
                query = query.options(option)
        result = await session.execute(query)
        records = cast(list[T], result.scalars().all())
        logger.debug(f"[DAO] Найдено {len(records)} записей.")
        return records

    @classmethod
    async def add(cls, session: AsyncSession, values: BaseModel) -> T:
        """Добавляет одну запись в базу данных."""
        values_dict = values.model_dump(exclude_unset=True)
        logger.debug(
            f"[DAO] Добавление записи {cls.model.__name__} с параметрами: "
            f"{cls._redact(values_dict)}"
        )
        try:
            new_instance = cast(T, cls.model(**values_dict))  # type: ignore [redundant-cast]
            session.add(new_instance)
            await session.flush()
            await session.refresh(new_instance)
            logger.info(
                f"[DAO] Запись {cls.model.__name__} id={new_instance.id} добавлена."
            )
            return new_instance
        except SQLAlchemyError as e:
            logger.exception(
                f"[DAO] Ошибка при добавлении записи {cls.model.__name__}: {type(e).__name__}"
            )
            raise

    @classmethod
    async def update(
        cls, session: AsyncSession, filters: BaseModel, values: BaseModel
    ) -> int:
        """Обновляет записи по фильтрам."""
        filter_dict = cls._to_dict(filters=filters)
        values_dict = cls._values_to_dict(values=values)
        logger.debug(
            f"[DAO] Обновление записей {cls.model.__name__} по фильтру: "
            f"{cls._redact(filter_dict)} с параметрами: {cls._redact(values_dict)}"
        )

        if not filter_dict:
            logger.error("[DAO] Нужен хотя бы один фильтр для обновления.")
            raise ValueError("Нужен хотя бы один фильтр для обновления.")

        filters_clause = cls._build_filters(filter_dict)
        query = (
            sqlalchemy_update(cls.model)
            .where(filters_clause)
            .values(**values_dict)
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = await session.execute(query)
            rowcount: int = getattr(result, "rowcount", 0) or 0

            logger.info(f"[DAO] Обновлено {rowcount} записей {cls.model.__name__}.")

            return rowcount or 0
        except SQLAlchemyError as e:
            logger.exception(
                f"[DAO] Ошибка при обновлении записей {cls.model.__name__}: {type(e).__name__}"
            )
            raise

    @classmethod
    async def delete(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Удаляет записи по фильтрам."""
        filter_dict = cls._to_dict(filters)
        logger.debug(
            f"[DAO] Удаление записей {cls.model.__name__} по фильтру: "
            f"{cls._redact(filter_dict)}"
        )
        if not filter_dict:
            logger.error("[DAO] Нужен хотя бы один фильтр для удаления.")
            raise ValueError("Нужен хотя бы один фильтр для удаления.")
        try:
            filters_clause = cls._build_filters(filter_dict)
            query = delete(cls.model).where(filters_clause)
            result = await session.execute(query)
            rowcount: int = getattr(result, "rowcount", 0) or 0
            logger.info(f"[DAO] Удалено {rowcount} записей {cls.model.__name__}.")
            return rowcount or 0
        except SQLAlchemyError as e:
            logger.exception(
                f"[DAO] Ошибка при удалении записей {cls.model.__name__}: {type(e).__name__}"
            )
            raise

    @classmethod
    async def add_many(
        cls, session: AsyncSession, instances: Sequence[BaseModel]
    ) -> list[T]:
        """Добавляет несколько записей в базу данных."""
        values_list = [cls._to_dict(item) for item in instances]
        logger.info(
            f"[DAO] Добавление нескольких записей {cls.model.__name__}. Количество: {len(values_list)}"
        )
        try:
            new_instances = [cls.model(**values) for values in values_list]
            session.add_all(new_instances)
            await session.flush()
            logger.info(
                f"[DAO] Успешно добавлено {len(new_instances)} записей {cls.model.__name__}."
            )
            return new_instances
        except SQLAlchemyError as e:
            logger.exception(
                f"[DAO] Ошибка при добавлении нескольких записей {cls.model.__name__}: {type(e).__name__}"
            )
            raise

    @classmethod
    async def count(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Подсчитывает количество записей по фильтрам."""
        filter_dict = cls._to_dict(filters=filters)
        logger.debug(
            f"[DAO] Подсчет количества записей {cls.model.__name__} по фильтру: "
            f"{cls._redact(filter_dict)}"
        )

        filters_clause = cls._build_filters(filter_dict)
        query = select(func.count(cls.model.id)).where(filters_clause)
        result = await session.execute(query)
        count = cast(int, result.scalar())
        logger.debug(f"[DAO] Найдено {count} записей.")
        return count or 0

    @classmethod
    async def find_by_ids(cls, session: AsyncSession, ids: list[int]) -> list[T]:
        """Находит несколько записей по списку ID."""
        logger.debug(f"[DAO] Поиск записей {cls.model.__name__} по списку ID: {ids}")
        if not ids:
            return []

        query = select(cls.model).where(cls.model.id.in_(ids))
        result = await session.execute(query)
        records = cast(list[T], result.scalars().all())
        logger.debug(f"[DAO] Найдено {len(records)} записей по списку ID.")
        return records
