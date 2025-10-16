import datetime
from typing import Any, List, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database import Base, int_pk, str_null_true, str_uniq


class UserRole(Base):
    """Модель связи пользователей и ролей.

    Представляет промежуточную таблицу для связи многие-ко-многим
    между пользователями и ролями.

    Attributes
        user_id (int): Идентификатор пользователя (внешний ключ на users.id).
        role_id (int): Идентификатор роли (внешний ключ на roles.id).
        user (User): Связанный пользователь.
        role (Role): Связанная роль.

    """

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )

    user: Mapped["User"] = relationship(back_populates="user_roles")
    role: Mapped["Role"] = relationship(back_populates="role_users")


def create_user_role(role: "Role") -> "UserRole":
    """Создаёт объект связи между пользователем и ролью.

    Args:
        role (Role): Роль, которую нужно связать с пользователем.

    Returns
        UserRole: Новый объект связи для добавления в коллекцию `user_roles`.

    """
    return UserRole(role=role)


class User(Base):
    """Модель пользователя, представляющая запись в таблице пользователей.

    Attributes
        id (int): Уникальный идентификатор пользователя.
        telegram_id (int): Идентификатор пользователя в Telegram.
        username (str | None): Имя пользователя в Telegram.
        first_name (str | None): Имя пользователя.
        last_name (str | None): Фамилия пользователя.
        user_roles (List[UserRole]): Промежуточные связи между пользователем и ролями.
        roles (List[Role]): Роли пользователя (association proxy).

    """

    id: Mapped[int_pk]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str_uniq]
    first_name: Mapped[str_null_true]
    last_name: Mapped[str_null_true]

    user_roles: Mapped[List["UserRole"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        passive_deletes=True,
    )
    roles: AssociationProxy[Any] = association_proxy(
        "user_roles", "role", creator=create_user_role
    )
    subscription: Mapped["Subscription"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __str__(self) -> str:
        """Строковое представление для записи."""
        return f"{self.first_name} {self.last_name} (@{self.username})"


class Role(Base):
    """Модель роли пользователя.

    Attributes
        id (int): Уникальный идентификатор роли.
        name (str): Уникальное имя роли.
        description (str | None): Описание роли.
        role_users (List[UserRole]): Промежуточные связи между ролями и пользователями.
        users (List[User]): Пользователи, связанные с ролью (association proxy).

    """

    id: Mapped[int_pk]
    name: Mapped[str_uniq]
    description: Mapped[str_null_true]

    role_users: Mapped[list["UserRole"]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )
    users: AssociationProxy[List["User"]] = association_proxy("role_users", "user")

    def __str__(self) -> str:
        """Строковое представление для записи."""
        return f"{self.name} - {self.description}"


class Subscription(Base):
    """Модель подписки пользователя.

    Хранит статус, дату начала и окончания действия подписки.
    Связана с пользователем отношением один-к-одному.

    Attributes
        id (int): Уникальный идентификатор записи.
        user_id (int): Внешний ключ на пользователя.
        is_active (bool): Флаг активности подписки.
        start_date (datetime): Дата начала подписки.
        end_date (datetime | None): Дата окончания подписки (None — бессрочная).
        user (User): Пользователь, владелец подписки.

    """

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(default=False)
    start_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
    )
    end_date: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="subscription")

    def __str__(self) -> str:
        """Строковое представление."""
        status = "Активна" if self.is_active else "Неактивна"
        until = (
            self.end_date.strftime("%Y-%m-%d %H:%M") if self.end_date else "бессрочная"
        )
        return f"{status} (до {until})"

    def activate(self, days: int) -> None:
        """Активирует подписку на указанное количество дней."""
        self.is_active = True
        self.start_date = datetime.datetime.now()
        self.end_date = self.start_date + datetime.timedelta(days=days)

    def deactivate(self) -> None:
        """Деактивирует подписку."""
        self.is_active = False
        self.end_date = datetime.datetime.now()

    def is_expired(self) -> bool:
        """Проверяет, истекла ли подписка.

        Returns
            bool: True, если срок подписки истёк или она неактивна.

        """
        if not self.is_active:
            return True
        if self.end_date and datetime.datetime.now() > self.end_date:
            return True
        return False

    def remaining_days(self) -> Optional[int]:
        """Возвращает количество оставшихся дней до окончания.

        Returns
            int | None: Количество дней или None, если подписка бессрочная.

        """
        if not self.end_date:
            return None
        delta = self.end_date - datetime.datetime.now()
        return max(delta.days, 0)
