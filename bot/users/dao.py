import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.admin.enums import FilterTypeEnum
from bot.app_error.base_error import SubscriptionNotFoundError
from bot.config import logger
from bot.dao.base import BaseDAO
from bot.subscription.models import Subscription, SubscriptionType
from bot.users.models import Role, User
from bot.users.schemas import SRole, SUser


class UserDAO(BaseDAO[User]):
    """Класс для работы с данными пользователей в базе данных.

    Наследует методы от BaseDAO и предоставляет дополнительные
    операции для работы с пользователями.

    Attributes
        model (User): Модель, с которой работает этот DAO.

    """

    model = User  # Модель для работы с данными пользователя

    @classmethod
    async def add_role_subscription(
        cls,
        session: AsyncSession,
        values_user: SUser,
        values_role: SRole,
    ) -> User:
        """Добавляет пользователя в БД + добавляется Роль и подписка.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            values_user (SUser): Значения для новой записи пользователя.
            values_role (SRole): Значения для присвоения роли.


        Returns
            User: Добавленная запись.

        """
        user_dict = values_user.model_dump(exclude_unset=True)
        role_dict = values_role.model_dump(exclude_unset=True)

        logger.info(
            f"[DAO] Добавление записи {cls.model.__name__} с параметрами: "
            f"Пользователь: {user_dict}, Роль: {role_dict}"
        )
        try:
            async with cls.transaction(session=session):
                role = await session.scalar(
                    select(Role).where(Role.name == role_dict["name"])
                )
                if not role:
                    logger.error(f"Роль '{role_dict['name']}' не найдена в БД")
                    raise ValueError(f"Роль '{role_dict['name']}' не найдена в БД")
                new_user = cls.model(**user_dict)
                session.add(new_user)
                await session.flush()
                subscription = Subscription(user_id=new_user.id)
                new_user.role = role
                new_user.subscription = subscription
                if role.name == "admin":
                    subscription.is_active = True
                    subscription.end_date = None
                    subscription.type = SubscriptionType.PREMIUM
                session.add(subscription)
                await session.refresh(
                    new_user, attribute_names=["subscription", "vpn_configs", "role"]
                )
                logger.debug(f"[DAO] Запись {cls.model.__name__} успешно добавлена.")
                return new_user
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при добавлении записи: {e}")
            raise e

    @classmethod
    async def get_users_by_roles(
        cls, session: AsyncSession, filter_type: str
    ) -> list[User]:
        """Получает список пользователей, отфильтрованных по роли.

        Функция выполняет запрос к базе данных с опциональной фильтрацией
        по роли. Если `filter_type` равен `"all"`, возвращаются все
        пользователи. В противном случае — только пользователи с указанной ролью.

        Args:
            session (AsyncSession): Активная асинхронная сессия SQLAlchemy.
            filter_type (str): Имя роли для фильтрации или `"all"`.

        Returns
            list[User]: Список найденных пользователей.

        Raises
            SQLAlchemyError: Ошибка выполнения запроса или работы транзакции.

        """
        try:
            async with cls.transaction(session=session):
                stmt = select(User).join(User.role).options(selectinload(User.role))
                if filter_type != "all":
                    stmt = stmt.where(Role.name == filter_type)

                result = await session.execute(stmt)
                return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка получения записи: {e}")
            raise e

    @classmethod
    async def change_role(
        cls,
        session: AsyncSession,
        user: User,
        role: Role,
    ) -> User:
        """Изменяет роль пользователя и при необходимости активирует подписку.

        Если новая роль равна ``FilterTypeEnum.FOUNDER``, пользователю
        автоматически активируется подписка до конца текущего года, а тип
        подписки меняется на ``SubscriptionType.PREMIUM``.

        Args:
            session (AsyncSession): Активная асинхронная сессия SQLAlchemy.
            user (User): Объект пользователя, чья роль изменяется.
            role (Role): Новая роль, которая будет назначена пользователю.

        Returns
            User: Обновлённый объект пользователя.

        Raises
            SQLAlchemyError: Ошибка при сохранении изменений в базе данных.

        """
        try:
            async with cls.transaction(session=session):
                user.role = role

                if role.name == FilterTypeEnum.FOUNDER:
                    now = datetime.datetime.now(tz=datetime.UTC)
                    next_year = datetime.datetime(
                        now.year + 1, 1, 1, tzinfo=datetime.UTC
                    )
                    delta = next_year - now
                    user.subscription.activate(days=delta.days)
                    user.subscription.type = SubscriptionType.PREMIUM
                await session.commit()
                return user
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка изменения роли пользователя: {e}")
            raise e

    @classmethod
    async def extend_subscription(
        cls, session: AsyncSession, user: User, months: int
    ) -> User:
        """Продляет активную подписку пользователя на указанное количество месяцев.

        Если подписка активна, её срок продляется. Если подписка не активна,
        возбуждается ``SubscriptionNotFoundError``.

        Args:
            session (AsyncSession): Активная асинхронная сессия SQLAlchemy.
            user (User): Пользователь, чья подписка продлевается.
            months (int): Количество месяцев для продления.

        Returns
            User: Объект пользователя с обновлённой подпиской.

        Raises
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.
            SQLAlchemyError: Ошибка сохранения данных в базе.

        """
        try:
            async with cls.transaction(session=session):
                subscription = user.subscription
                if subscription.is_active:
                    subscription.extend(months=months)
                else:
                    raise SubscriptionNotFoundError(user_id=user.telegram_id)
                await session.commit()
            return user

        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при продлении подписки пользователя: {e}")
            raise e

    @classmethod
    async def find_one_or_none(
        cls, session: AsyncSession, filters: BaseModel
    ) -> User | None:
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
        async with cls.transaction(session):
            filters_clause = cls._build_filters(filter_dict)
            # noinspection PyTypeChecker
            query = (
                select(cls.model)
                .where(filters_clause)
                .options(
                    selectinload(cls.model.role),
                    selectinload(cls.model.subscription),
                    selectinload(cls.model.subscription),
                )
            )
            result = await session.execute(query)
            record = result.scalar_one_or_none()
            logger.debug(f"[DAO] Найдено: {record!r}")
            return record


class RoleDAO(BaseDAO[Role]):
    """Класс DAO для работы с ролями пользователей.

    Наследует общие методы из `BaseDAO` и обеспечивает доступ к данным
    таблицы `roles`.

    Attributes
        model (type[Role]): Модель ORM, с которой работает данный DAO.

    """

    model = Role
