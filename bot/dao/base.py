from typing import (
    Any,
    Generic,
    TypeVar,
    cast,
)

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import and_, delete, func, select
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import Base

# Объявляем типовой параметр T с ограничением, что это наследник Base
T = TypeVar("T", bound=Base)


class BaseDAO(Generic[T]):  # noqa: UP046
    """Общий класс для работы с объектами моделей в базе данных.

    Этот класс предоставляет базовые методы для выполнения операций
    CRUD (создание, чтение, обновление, удаление)
    для моделей, унаследованных от него. Он использует
    асинхронные сессии SQLAlchemy.

    Attributes
        model (Type[T]): Модель, с которой работает данный DAO.
        Это должен быть тип модели,
                          указанный в дочернем классе.



    """

    # noinspection PyTypeHints
    model: type[T]  # Тип модели, которой управляет этот DAO

    @staticmethod
    def _to_dict(filters: BaseModel | None) -> dict[str, Any]:
        """Преобразование в словарь BaseModel схему."""
        return filters.model_dump(exclude_unset=True) if filters else {}

    @classmethod
    def _build_filters(cls, f: dict[str, Any]) -> list[Any]:
        """Построение фильтров для SQLAlchemy из словаря."""
        return [getattr(cls.model, k) == v for k, v in f.items()]

    @staticmethod
    async def _commit(session: AsyncSession) -> None:
        """Коммит изменений в сессии с обработкой ошибок."""
        try:
            await session.commit()
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка коммита: {e}")
            await session.rollback()
            raise

    @classmethod
    async def find_one_or_none_by_id(
        cls, data_id: int, session: AsyncSession
    ) -> T | None:
        """Находит запись по ID.

        Args:
            data_id (int): Идентификатор записи.
            session (AsyncSession): Сессия для взаимодействия с БД.

        Returns
            Optional[T]: Запись с указанным ID или None, если запись не найдена.

        """
        # noinspection PyTypeChecker
        logger.info(f"[DAO] Поиск {cls.model.__name__} с ID: {data_id}")

        # noinspection PyTypeChecker
        query = select(cls.model).where(cls.model.id == data_id)  # type: ignore[attr-defined]

        result = await session.execute(query)
        record = cast(T | None, result.scalar_one_or_none())  # type: ignore[redundant-cast]
        logger.debug(f"[DAO] Результат поиска id={data_id}: {record!r}")
        return record

    @classmethod
    async def find_one_or_none(
        cls, session: AsyncSession, filters: BaseModel
    ) -> T | None:
        """Находит одну запись по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для поиска.

        Returns
            Optional[T]: Найденная запись или None.

        """
        filter_dict = cls._to_dict(filters=filters)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Поиск одной записи {cls.model.__name__} по фильтрам: {filter_dict}"
        )
        logger.debug(f"[DAO] Фильтры → условия: {cls._build_filters(filter_dict)}")
        # noinspection PyTypeChecker
        query = select(cls.model).where(and_(*cls._build_filters(filter_dict)))
        result = await session.execute(query)
        record = cast(T | None, result.scalar_one_or_none())  # type: ignore[redundant-cast]
        logger.debug(f"[DAO] Найдено: {record!r}")
        return record

    @classmethod
    async def find_all(
        cls, session: AsyncSession, filters: BaseModel | None = None
    ) -> list[T]:
        """Находит все записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для поиска./или без фильтар

        Returns
            List[T]: Список найденных записей.

        """
        filter_dict = cls._to_dict(filters=filters)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Поиск всех записей {cls.model.__name__} по фильтрам: {filter_dict}"
        )
        # noinspection PyTypeChecker
        query = select(cls.model).where(and_(*cls._build_filters(filter_dict)))
        result = await session.execute(query)
        records = cast(list[T], result.scalars().all())
        logger.debug(f"[DAO] Найдено {len(records)} записей.")
        return records

    @classmethod
    async def add(cls, session: AsyncSession, values: BaseModel) -> T:
        """Добавляет одну запись в базу данных.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            values (BaseModel): Значения для новой записи.

        Returns
            T: Добавленная запись.

        """
        values_dict = values.model_dump(exclude_unset=True)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Добавление записи {cls.model.__name__} с параметрами: {values_dict}"
        )
        # noinspection PyTypeChecker
        new_instance = cast(T, cls.model(**values_dict))  # type: ignore [redundant-cast]
        session.add(new_instance)
        await cls._commit(session)
        logger.debug(f"[DAO] Запись {cls.model.__name__} успешно добавлена.")
        return new_instance

    @classmethod
    async def update(
        cls, session: AsyncSession, filters: BaseModel, values: BaseModel
    ) -> int:
        """Обновляет записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для обновления.
            values (BaseModel): Новые значения для обновленных записей.

        Returns
            int: Количество обновленных записей.

        """
        filter_dict = cls._to_dict(filters=filters)
        values_dict = cls._to_dict(filters=values)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Обновление записей {cls.model.__name__} по фильтру: "
            f"{filter_dict} с параметрами: {values_dict}"
        )
        # noinspection PyTypeChecker
        query = (
            sqlalchemy_update(cls.model)
            .where(*cls._build_filters(filter_dict))
            .values(**values_dict)
            .execution_options(synchronize_session="fetch")
        )

        result = await session.execute(query)
        await cls._commit(session)
        rowcount: int = getattr(result, "rowcount", 0) or 0

        logger.debug(f"[DAO] Обновлено {rowcount} записей.")

        return rowcount or 0

    @classmethod
    async def delete(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Удаляет записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для удаления.

        Returns
            int: Количество удаленных записей.

        """
        filter_dict = cls._to_dict(filters)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Удаление записей {cls.model.__name__} по фильтру: {filter_dict}"
        )
        if not filter_dict:
            logger.error("[DAO] Нужен хотя бы один фильтр для удаления.")
            raise ValueError("Нужен хотя бы один фильтр для удаления.")
        # noinspection PyTypeChecker
        query = delete(cls.model).where(and_(*cls._build_filters(filter_dict)))
        result = await session.execute(query)
        await cls._commit(session)
        rowcount: int = getattr(result, "rowcount", 0) or 0
        logger.info(f"[DAO] Удалено {rowcount} записей.")
        return rowcount or 0

    @classmethod
    async def add_many(
        cls, session: AsyncSession, instances: list[BaseModel]
    ) -> list[T]:
        """Добавляет несколько записей в базу данных.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            instances (List[BaseModel]): Список значений для новых записей.

        Returns
            List[T]: Список добавленных записей.

        """
        values_list = [cls._to_dict(item) for item in instances]
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Добавление нескольких записей {cls.model.__name__}. Количество: {len(values_list)}"
        )
        # noinspection PyTypeChecker
        new_instances = [cls.model(**values) for values in values_list]
        session.add_all(new_instances)
        await cls._commit(session)
        logger.info(f"[DAO] Успешно добавлено {len(new_instances)} записей.")
        return new_instances

    @classmethod
    async def count(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Подсчитывает количество записей по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для подсчета.

        Returns
            int: Количество записей.

        """
        filter_dict = cls._to_dict(filters=filters)
        # noinspection PyTypeChecker
        logger.info(
            f"[DAO] Подсчет количества записей {cls.model.__name__} по фильтру: {filter_dict}"
        )
        # noinspection PyTypeChecker
        query = select(func.count(cls.model.id)).where(
            and_(*cls._build_filters(filter_dict))
        )  # type: ignore
        result = await session.execute(query)
        count = cast(int, result.scalar())
        logger.debug(f"[DAO] Найдено {count} записей.")
        return count or 0

    @classmethod
    async def find_by_ids(cls, session: AsyncSession, ids: list[int]) -> list[T]:
        """Находит несколько записей по списку ID.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            ids (List[int]): Список ID для поиска.

        Returns
            List[T]: Список найденных записей.

        """
        # noinspection PyTypeChecker
        logger.info(f"[DAO] Поиск записей {cls.model.__name__} по списку ID: {ids}")
        if not ids:
            return []

        # noinspection PyTypeChecker
        query = select(cls.model).where(cls.model.id.in_(ids))  # type: ignore[attr-defined]
        result = await session.execute(query)
        records = cast(list[T], result.scalars().all())
        logger.debug(f"[DAO] Найдено {len(records)} записей по списку ID.")
        return records
