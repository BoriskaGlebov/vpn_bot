from typing import TYPE_CHECKING, Any, List

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.ext.associationproxy import AssociationProxy, association_proxy
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database import Base, int_pk, str_null_true, str_uniq

if TYPE_CHECKING:
    from bot.subscription.models import Subscription  # импорт только для type hints


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

    user: Mapped["User"] = relationship(back_populates="user_roles", lazy="selectin")
    role: Mapped["Role"] = relationship(back_populates="role_users", lazy="selectin")


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
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
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
