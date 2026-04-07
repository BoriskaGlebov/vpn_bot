from typing import Any

from sqlalchemy import BigInteger, ForeignKey, ScalarSelect, case, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

# TODO преезарегитсрировать модели и настройки
from api.core.database import Base, int_pk, str_null_true, str_uniq
from api.referrals.models import Referral
from api.subscription.models import Subscription
from api.vpn.models import VPNConfig


class User(Base):
    """Модель пользователя.

    Attributes
        id (int): Уникальный идентификатор пользователя.
        telegram_id (int): Идентификатор пользователя в Telegram.
        username (str | None): Username пользователя.
        first_name (str | None): Имя пользователя.
        last_name (str | None): Фамилия пользователя.
        role_id (int | None): FK на роль.
        role (Role): Связанная роль.
        subscriptions (list[Subscription]): Список подписок пользователя.
        vpn_configs (list[VPNConfig]): VPN-конфиги пользователя.
        invited_users (list[Referral]): Рефералы, приглашённые пользователем.
        invited_by (Referral | None): Кто пригласил пользователя.
        has_used_trial (bool): Использовал ли пользователь триал.

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
    invited_users: Mapped[list["Referral"]] = relationship(
        "Referral",
        foreign_keys=[Referral.inviter_id],
        back_populates="inviter",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    invited_by: Mapped["Referral | None"] = relationship(
        "Referral",
        foreign_keys=[Referral.invited_id],
        back_populates="invited",
        uselist=False,
        lazy="selectin",
    )

    def __str__(self) -> str:
        """Строковое представление для записи."""
        parts = [
            self.first_name or "",
            self.last_name or "",
            f"@{self.username}" if self.username else "",
        ]
        return " ".join(p for p in parts if p)

    @property
    def current_subscription(self) -> "Subscription | None":
        """Возвращает текущую (приоритетную) подписку пользователя.

        Подписки отсортированы таким образом, что первая запись является
        наиболее приоритетной (активная, затем по типу и дате окончания).

        Returns
            Subscription | None: Текущая подписка или None, если подписок нет.

        """
        if not self.subscriptions:
            return None

        return self.subscriptions[0]

    @hybrid_property
    def vpn_files_count(self) -> int:
        """Возвращает количество VPN конфигов, связанных с пользователем.

        Это обычный Python property, которое считает элементы в списке `vpn_configs`.

        Returns
            int: Количество VPN конфигов пользователя.

        """
        return len(self.vpn_configs)

    @vpn_files_count.expression  # type: ignore[no-redef]
    def vpn_files_count(cls) -> ScalarSelect[Any]:
        """SQL-выражение для подсчёта VPN-конфигов.

        Используется в ORM-запросах для сортировки и фильтрации без загрузки
        связанных объектов.

        Args:
            cls: Класс модели User (SQLAlchemy ORM context).

        Returns
            ScalarSelect[int]: Подзапрос с COUNT(VPNConfig.id).

        """
        return (
            select(func.count(VPNConfig.id))
            .where(VPNConfig.user_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def referrals_count(self) -> int:
        """Возвращает количество приглашённых пользователей.

        Returns
            int: Число рефералов.

        """
        return len(self.invited_users) if self.invited_users else 0

    @referrals_count.expression  # type: ignore[no-redef]
    def referrals_count(cls) -> ScalarSelect[Any]:
        """SQL-выражение для подсчёта рефералов.

        Args:
            cls: Класс модели User.

        Returns
            ScalarSelect[int]: Подзапрос с количеством рефералов.

        """
        return (
            select(func.count(Referral.id))
            .where(Referral.inviter_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def paid_referrals_count(self) -> int:
        """Возвращает количество рефералов, получивших бонус.

        Returns
            int: Количество рефералов с выданным бонусом.

        """
        if not self.invited_users:
            return 0

        return sum(1 for ref in self.invited_users if ref.bonus_given)

    @paid_referrals_count.expression  # type: ignore[no-redef]
    def paid_referrals_count(cls) -> ScalarSelect[int]:
        """SQL-выражение для подсчёта рефералов с бонусом.

        Args:
            cls: Класс модели User.

        Returns
            ScalarSelect[int]: Подзапрос с фильтром bonus_given = True.

        """
        return (
            select(func.count(Referral.id))
            .where(
                Referral.inviter_id == cls.id,
                Referral.bonus_given.is_(True),
            )
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def referral_conversion(self) -> float:
        """Вычисляет конверсию рефералов.

        Конверсия определяется как отношение количества рефералов,
        получивших бонус, к общему количеству рефералов.

        Returns
            float: Значение конверсии в диапазоне [0.0, 1.0].

        """
        if not self.referrals_count:
            return 0.0
        return self.paid_referrals_count / self.referrals_count


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

    @property
    def users_count(self) -> int:
        """Свойство отображает количество пользователй Роли."""
        return len(self.users) if self.users else 0
