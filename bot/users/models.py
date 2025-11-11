from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database import Base, int_pk, str_null_true, str_uniq

if TYPE_CHECKING:
    from bot.subscription.models import Subscription  # импорт только для type hints


class User(Base):
    """Модель пользователя.

    Атрибуты
        id (int): Уникальный идентификатор пользователя.
        telegram_id (int): Идентификатор пользователя в Telegram.
        username (str | None): Имя пользователя в Telegram.
        first_name (str | None): Имя пользователя.
        last_name (str | None): Фамилия пользователя.
        role_id (Optional[int]): Внешний ключ на роль. Может быть None.
        role (Role): Связанная роль пользователя.
        subscription (Subscription | None): Подписка пользователя. Может отсутствовать.

    """

    id: Mapped[int_pk]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str_uniq]
    first_name: Mapped[str_null_true]
    last_name: Mapped[str_null_true]

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="selectin")

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

    users: Mapped[list["User"]] = relationship(
        "User", back_populates="role", lazy="selectin"
    )

    def __str__(self) -> str:
        """Строковое представление для записи."""
        return f"{self.name} - {self.description}"
