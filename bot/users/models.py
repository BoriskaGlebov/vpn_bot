from sqlalchemy import BigInteger, ForeignKey, case
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database import Base, int_pk, str_null_true, str_uniq
from bot.subscription.models import Subscription  # импорт только для type hints
from bot.vpn.models import VPNConfig


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
        vpn_configs (list["VPNConfig"]): Список конфиг файлов пользователя.
        has_used_trial (bool): Проверка использовал пользователь триал или нет

    """

    id: Mapped[int_pk]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str_uniq]
    first_name: Mapped[str_null_true]
    last_name: Mapped[str_null_true]
    has_used_trial: Mapped[bool] = mapped_column(default=False, server_default="false")

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("roles.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users", lazy="selectin")

    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=True,
        lazy="selectin",
        order_by=lambda: (
            Subscription.is_active.desc(),
            case(
                (Subscription.type == "PREMIUM", 3),
                (Subscription.type == "STANDARD", 2),
                (Subscription.type == "TRIAL", 1),
                else_=0,
            ).desc(),
            Subscription.end_date.desc(),
        ),
    )
    vpn_configs: Mapped[list["VPNConfig"]] = relationship(
        "VPNConfig",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="VPNConfig.id",
    )

    def __str__(self) -> str:
        """Строковое представление для записи."""
        parts = [
            self.first_name or "",
            self.last_name or "",
            f"@{self.username}" if self.username else "",
        ]
        return " ".join(p for p in parts if p)


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
