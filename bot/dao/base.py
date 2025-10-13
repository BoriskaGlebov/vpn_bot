from typing import (
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    cast,
)

from pydantic import BaseModel
from sqlalchemy import delete as sqlalchemy_delete
from sqlalchemy import func
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from bot.config import logger
from bot.database import Base

# Объявляем типовой параметр T с ограничением, что это наследник Base
T = TypeVar("T", bound=Base)


class BaseDAO(Generic[T]):
    """Общий класс для работы с объектами моделей в базе данных.

    Этот класс предоставляет базовые методы для выполнения операций
    CRUD (создание, чтение, обновление, удаление)
    для моделей, унаследованных от него. Он использует
    асинхронные сессии SQLAlchemy.

    Attributes
        model (Type[T]): Модель, с которой работает данный DAO.
        Это должен быть тип модели,
                          указанный в дочернем классе.

    Methods
        find_one_or_none_by_id(data_id: int, session: AsyncSession) -> Optional[T]:
            Находит одну запись по ее ID.

        find_one_or_none(session: AsyncSession, filters: BaseModel) -> Optional[T]:
            Находит одну запись по фильтрам.

        find_all(session: AsyncSession, filters: BaseModel) -> List[T]:
            Находит все записи по фильтрам.

        add(session: AsyncSession, values: BaseModel) -> T:
            Добавляет новую запись в базу данных.

        add_many(session: AsyncSession, instances: List[BaseModel]) -> List[T]:
            Добавляет несколько записей в базу данных.

        update(session: AsyncSession, filters: BaseModel, values: BaseModel) -> int:
            Обновляет записи, соответствующие фильтрам.

        delete(session: AsyncSession, filters: BaseModel) -> int:
            Удаляет записи, соответствующие фильтрам.

        count(session: AsyncSession, filters: BaseModel) -> int:
            Подсчитывает количество записей по фильтрам.

        paginate(session: AsyncSession, page: int = 1,
        page_size: int = 10, filters: BaseModel = None) -> List[T]:
            Пагинирует записи по фильтрам, возвращая записи для указанной страницы.

        find_by_ids(session: AsyncSession, ids: List[int]) -> List[T]:
            Находит несколько записей по списку ID.

        upsert(session: AsyncSession, unique_fields: List[str], values: BaseModel) -> T:
            Выполняет операцию "upsert": создает запись, если
            она не существует, или обновляет существующую.

        bulk_update(session: AsyncSession, records: List[BaseModel]) -> int:
            Массово обновляет записи в базе данных.

    """

    # noinspection PyTypeHints
    model: Type[T]  # Тип модели, которой управляет этот DAO

    @classmethod
    async def find_one_or_none_by_id(
        cls, data_id: int, session: AsyncSession
    ) -> Optional[T]:
        """Находит запись по ID.

        Args:
            data_id (int): Идентификатор записи.
            session (AsyncSession): Сессия для взаимодействия с БД.

        Returns
            Optional[T]: Запись с указанным ID или None, если запись не найдена.

        """
        # noinspection PyTypeChecker
        logger.info(f"Поиск {cls.model.__name__} с ID: {data_id}")
        try:
            # noinspection PyTypeChecker
            query = select(cls.model).filter_by(id=data_id)
            result = await session.execute(query)
            record = cast(Optional[T], result.scalar_one_or_none())
            if record:
                logger.info(f"Запись с ID {data_id} найдена.")
            else:
                logger.info(f"Запись с ID {data_id} не найдена.")
            return record
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске записи с ID {data_id}: {e}")
            raise

    @classmethod
    async def find_one_or_none(
        cls, session: AsyncSession, filters: BaseModel
    ) -> Optional[T]:
        """Находит одну запись по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для поиска.

        Returns
            Optional[T]: Найденная запись или None.

        """
        filter_dict = filters.model_dump(exclude_unset=True)
        # noinspection PyTypeChecker
        logger.info(
            f"Поиск одной записи {cls.model.__name__} по фильтрам: {filter_dict}"
        )
        try:
            # noinspection PyTypeChecker
            query = select(cls.model).filter_by(**filter_dict)
            result = await session.execute(query)
            record = cast(Optional[T], result.scalar_one_or_none())
            if record:
                logger.info(f"Запись найдена по фильтрам: {filter_dict}")
            else:
                logger.info(f"Запись не найдена по фильтрам: {filter_dict}")
            return record
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске записи по фильтрам {filter_dict}: {e}")
            raise

    @classmethod
    async def find_all(
        cls, session: AsyncSession, filters: Optional[BaseModel] = None
    ) -> List[T]:
        """Находит все записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для поиска./или без фильтар

        Returns
            List[T]: Список найденных записей.

        """
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
        # noinspection PyTypeChecker
        logger.info(
            f"Поиск всех записей {cls.model.__name__} по фильтрам: {filter_dict}"
        )
        try:
            # noinspection PyTypeChecker
            query = select(cls.model).filter_by(**filter_dict)
            result = await session.execute(query)
            records = cast(List[T], result.scalars().all())
            logger.info(f"Найдено {len(records)} записей.")
            return records
        except SQLAlchemyError as e:
            logger.error(
                f"Ошибка при поиске всех записей по фильтрам {filter_dict}: {e}"
            )
            raise

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
            f"Добавление записи {cls.model.__name__} с параметрами: {values_dict}"
        )
        # noinspection PyTypeChecker
        new_instance = cast(T, cls.model(**values_dict))
        session.add(new_instance)
        try:
            await session.commit()
            # noinspection PyTypeChecker
            logger.info(f"Запись {cls.model.__name__} успешно добавлена.")
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении записи: {e}")
            raise e
        return new_instance

    @classmethod
    async def add_many(
        cls, session: AsyncSession, instances: List[BaseModel]
    ) -> List[T]:
        """Добавляет несколько записей в базу данных.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            instances (List[BaseModel]): Список значений для новых записей.

        Returns
            List[T]: Список добавленных записей.

        """
        values_list = [item.model_dump(exclude_unset=True) for item in instances]
        # noinspection PyTypeChecker
        logger.info(
            f"Добавление нескольких записей {cls.model.__name__}. Количество: {len(values_list)}"
        )
        # noinspection PyTypeChecker
        new_instances = [cls.model(**values) for values in values_list]
        session.add_all(new_instances)
        try:
            await session.commit()
            logger.info(f"Успешно добавлено {len(new_instances)} записей.")
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при добавлении нескольких записей: {e}")
            raise e
        return new_instances

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
        filter_dict = filters.model_dump(exclude_unset=True)
        values_dict = values.model_dump(exclude_unset=True)
        # noinspection PyTypeChecker
        logger.info(
            f"Обновление записей {cls.model.__name__} по фильтру: "
            f"{filter_dict} с параметрами: {values_dict}"
        )
        # noinspection PyTypeChecker
        query = (
            sqlalchemy_update(cls.model)
            .where(*[getattr(cls.model, k) == v for k, v in filter_dict.items()])
            .values(**values_dict)
            .execution_options(synchronize_session="fetch")
        )
        try:
            result = await session.execute(query)
            await session.commit()
            rowcount: int = getattr(result, "rowcount", 0) or 0
            if rowcount:
                logger.info(f"Обновлено {rowcount} записей.")

            return rowcount or 0
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при обновлении записей: {e}")
            raise e

    @classmethod
    async def delete(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Удаляет записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для удаления.

        Returns
            int: Количество удаленных записей.

        """
        filter_dict = filters.model_dump(exclude_unset=True)
        # noinspection PyTypeChecker
        logger.info(f"Удаление записей {cls.model.__name__} по фильтру: {filter_dict}")
        if not filter_dict:
            logger.error("Нужен хотя бы один фильтр для удаления.")
            raise ValueError("Нужен хотя бы один фильтр для удаления.")
        # noinspection PyTypeChecker
        query = sqlalchemy_delete(cls.model).filter_by(**filter_dict)
        try:
            result = await session.execute(query)
            await session.commit()
            rowcount: int = getattr(result, "rowcount", 0) or 0
            if rowcount:
                logger.info(f"Удалено {rowcount} записей.")
            return rowcount or 0
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при удалении записей: {e}")
            raise e

    @classmethod
    async def count(cls, session: AsyncSession, filters: BaseModel) -> int:
        """Подсчитывает количество записей по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            filters (BaseModel): Фильтры для подсчета.

        Returns
            int: Количество записей.

        """
        filter_dict = filters.model_dump(exclude_unset=True)
        # noinspection PyTypeChecker
        logger.info(
            f"Подсчет количества записей {cls.model.__name__} по фильтру: {filter_dict}"
        )
        try:
            # noinspection PyTypeChecker
            query = select(func.count(cls.model.id)).filter_by(**filter_dict)
            result = await session.execute(query)
            count = cast(int, result.scalar())
            logger.info(f"Найдено {count} записей.")
            return count
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при подсчете записей: {e}")
            raise

    @classmethod
    async def paginate(
        cls,
        session: AsyncSession,
        page: int = 1,
        page_size: int = 10,
        filters: BaseModel | None = None,
    ) -> List[T]:
        """Пагинирует записи по фильтрам.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            page (int): Номер страницы.
            page_size (int): Размер страницы.
            filters (Optional[BaseModel]): Фильтры для поиска (по умолчанию None).

        Returns
            List[T]: Список записей на текущей странице.

        """
        filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
        # noinspection PyTypeChecker
        logger.info(
            f"Пагинация записей {cls.model.__name__} по фильтру: {filter_dict}, "
            f"страница: {page}, размер страницы: {page_size}"
        )
        try:
            # noinspection PyTypeChecker
            query = select(cls.model).filter_by(**filter_dict)
            result = await session.execute(
                query.offset((page - 1) * page_size).limit(page_size)
            )
            records = cast(List[T], result.scalars().all())
            logger.info(f"Найдено {len(records)} записей на странице {page}.")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при пагинации записей: {e}")
            raise

    @classmethod
    async def find_by_ids(cls, session: AsyncSession, ids: List[int]) -> List[T]:
        """Находит несколько записей по списку ID.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            ids (List[int]): Список ID для поиска.

        Returns
            List[T]: Список найденных записей.

        """
        # noinspection PyTypeChecker
        logger.info(f"Поиск записей {cls.model.__name__} по списку ID: {ids}")
        try:
            # noinspection PyTypeChecker
            query = select(cls.model).filter(cls.model.id.in_(ids))
            result = await session.execute(query)
            records = cast(List[T], result.scalars().all())
            logger.info(f"Найдено {len(records)} записей по списку ID.")
            return records
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при поиске записей по списку ID: {e}")
            raise

    @classmethod
    async def upsert(
        cls, session: AsyncSession, unique_fields: List[str], values: BaseModel
    ) -> T:
        """Создает запись или обновляет существующую.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            unique_fields (List[str]): Поля, которые определяют уникальность записи.
            values (BaseModel): Новые значения для записи.

        Returns
            T: Созданная или обновленная запись.

        """
        values_dict = values.model_dump(exclude_unset=True)
        filter_dict = {
            field: values_dict[field] for field in unique_fields if field in values_dict
        }
        # noinspection PyTypeChecker
        logger.info(f"Upsert для {cls.model.__name__}")
        try:
            existing = await cls.find_one_or_none(
                session, values.__class__(**filter_dict)
            )
            if existing:
                # Обновляем существующую запись
                for key, value in values_dict.items():
                    setattr(existing, key, value)
                await session.commit()
                # noinspection PyTypeChecker
                logger.info(f"Обновлена существующая запись {cls.model.__name__}")
                return existing
            else:
                # noinspection PyTypeChecker
                new_instance = cast(T, cls.model(**values_dict))
                session.add(new_instance)
                await session.commit()
                # noinspection PyTypeChecker
                logger.info(f"Создана новая запись {cls.model.__name__}")
                return new_instance
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при upsert: {e}")
            raise

    @classmethod
    async def bulk_update(cls, session: AsyncSession, records: List[BaseModel]) -> int:
        """Массовое обновление записей.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            records (List[BaseModel]): Список записей для обновления.

        Returns
            int: Количество обновленных записей.

        """
        # noinspection PyTypeChecker
        logger.info(f"Массовое обновление записей {cls.model.__name__}")
        try:
            updated_count = 0
            for record in records:
                record_dict = record.model_dump(exclude_unset=True)
                if "id" not in record_dict:
                    continue

                update_data = {k: v for k, v in record_dict.items() if k != "id"}
                # noinspection PyTypeChecker
                stmt = (
                    sqlalchemy_update(cls.model)
                    .filter_by(id=record_dict["id"])
                    .values(**update_data)
                )
                result = await session.execute(stmt)
                rowcount: int = getattr(result, "rowcount", 0) or 0
                updated_count += rowcount

            await session.commit()
            logger.info(f"Обновлено {updated_count} записей")
            return updated_count
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Ошибка при массовом обновлении: {e}")
            raise e
