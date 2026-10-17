import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.app_error.base_error import RoleNotFoundError, SubscriptionNotFoundError
from api.core.dao.base import BaseDAO
from api.subscription.models import Subscription, SubscriptionType
from api.users.models import Role, User
from api.users.schemas import SRole, SUser
from shared.enums.admin_enum import RoleEnum


class UserDAO(BaseDAO[User]):
    """Класс для работы с данными пользователей в базе данных.

    Наследует методы от BaseDAO и предоставляет дополнительные
    операции для работы с пользователями.

    Attributes
        model (User): Модель, с которой работает этот DAO.

    """

    model = User
    base_options = [
        selectinload(User.role),
        selectinload(User.subscriptions),
        selectinload(User.vpn_configs),
    ]

    @classmethod
    async def add_role_subscription(
        cls,
        session: AsyncSession,
        values_user: SUser,
        values_role: SRole,
        *,
        subscription_is_active: bool = False,
        subscription_type: SubscriptionType | None = None,
        subscription_end_date: datetime.datetime | None = None,
    ) -> User:
        """Добавляет пользователя в БД + добавляется Роль и подписка.

        Начальное состояние подписки — чем решает вызывающий код (сервис),
        а не этот метод: DAO только сохраняет переданные значения и не
        содержит правил вроде «администратор получает бессрочный премиум»
        (см. #244). По умолчанию подписка неактивна, без типа — как и было
        до появления отдельной ветки для роли admin.

        Args:
            session (AsyncSession): Сессия для взаимодействия с БД.
            values_user (SUser): Значения для новой записи пользователя.
            values_role (SRole): Значения для присвоения роли.
            subscription_is_active (bool): Начальная активность подписки.
            subscription_type (SubscriptionType | None): Начальный тип подписки.
            subscription_end_date (datetime.datetime | None): Дата окончания
                подписки (None — бессрочная/не задана).

        Returns
            User: Добавленная запись.

        Raises
            RoleNotFoundError: Если роль с переданным именем не найдена в БД.

        """
        user_dict = values_user.model_dump(exclude_unset=True)
        role_dict = values_role.model_dump(exclude_unset=True)

        logger.info(
            f"[DAO] Добавление записи {cls.model.__name__} с параметрами: "
            f"Пользователь: {cls._redact(user_dict)}, Роль: {cls._redact(role_dict)}"
        )
        try:
            role = await session.scalar(
                select(Role).where(Role.name == role_dict["name"])
            )
            if not role:
                logger.error(f"Роль '{role_dict['name']}' не найдена в БД")
                raise RoleNotFoundError(role_name=role_dict["name"])
            new_user = cls.model(**user_dict)
            session.add(new_user)
            await session.flush()
            subscription = Subscription(
                user_id=new_user.id,
                is_active=subscription_is_active,
                type=subscription_type,
                end_date=subscription_end_date,
            )
            new_user.role = role
            session.add(subscription)
            await session.flush()
            await session.refresh(
                new_user, attribute_names=["subscriptions", "vpn_configs", "role"]
            )
            logger.debug(f"[DAO] Запись {cls.model.__name__} успешно добавлена.")
            return new_user
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при добавлении записи: {e}")
            raise

    @classmethod
    async def get_users_by_roles(
        cls, session: AsyncSession, filter_type: str
    ) -> list[User]:
        """Получает список пользователей, отфильтрованных по роли.

        Функция выполняет запрос к базе данных с опциональной фильтрацией
        по роли. Если `filter_type` равен `RoleEnum.ALL`, возвращаются все
        пользователи. В противном случае — только пользователи с указанной ролью.

        Args:
            session (AsyncSession): Активная асинхронная сессия SQLAlchemy.
            filter_type (str): Имя роли для фильтрации или `RoleEnum.ALL`.

        Returns
            list[User]: Список найденных пользователей.

        Raises
            SQLAlchemyError: Ошибка выполнения запроса или работы транзакции.

        """
        try:
            stmt = select(User).join(User.role).options(selectinload(User.role))
            if filter_type != RoleEnum.ALL:
                stmt = stmt.where(Role.name == filter_type)

            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка получения записи: {e}")
            raise

    @classmethod
    async def get_telegram_ids_excluding_role(
        cls, session: AsyncSession, role_name: RoleEnum
    ) -> list[int]:
        """Возвращает Telegram ID всех пользователей, кроме указанной роли.

        В отличие от `get_users_by_roles` (фильтрация по совпадению роли,
        полные объекты `User`), здесь — фильтрация по исключению роли и
        проекция сразу на `telegram_id` (используется для рассылок, где
        полные объекты пользователей не нужны).

        Args:
            session (AsyncSession): Активная асинхронная сессия SQLAlchemy.
            role_name (RoleEnum): Имя роли, пользователей с которой нужно исключить.

        Returns
            list[int]: Telegram ID пользователей, не имеющих указанную роль.

        Raises
            SQLAlchemyError: Ошибка выполнения запроса или работы транзакции.

        """
        try:
            stmt = (
                select(User.telegram_id).join(User.role).where(Role.name != role_name)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка получения записи: {e}")
            raise

    @classmethod
    async def change_role(
        cls,
        session: AsyncSession,
        user: User,
        role: Role,
    ) -> User:
        """Изменяет роль пользователя и при необходимости активирует подписку.

        Если новая роль равна ``RoleEnum.FOUNDER``, пользователю
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
            user.role = role
            return user
        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка изменения роли пользователя: {e}")
            raise

    @classmethod
    async def extend_subscription(
        cls,
        session: AsyncSession,
        user: User,
        months: int,
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
            subscription = user.subscriptions[0]
            if subscription.is_active:
                subscription.extend(months=months)
            else:
                raise SubscriptionNotFoundError(user_id=user.id, username=user.username)
            return user

        except SQLAlchemyError as e:
            logger.error(f"[DAO] Ошибка при продлении подписки пользователя: {e}")
            raise


class RoleDAO(BaseDAO[Role]):
    """Класс DAO для работы с ролями пользователей.

    Наследует общие методы из `BaseDAO` и обеспечивает доступ к данным
    таблицы `roles`.

    Attributes
        model (type[Role]): Модель ORM, с которой работает данный DAO.

    """

    model = Role
