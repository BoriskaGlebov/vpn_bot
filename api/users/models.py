from typing import Any

from sqlalchemy import BigInteger, ForeignKey, ScalarSelect, case, func, select
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, int_pk, str_null_true, str_uniq
from api.payment.model import PaymentTransaction
from api.referrals.models import Referral
from api.subscription.models import SUBSCRIPTION_PRIORITY, Subscription
from api.vpn.models import VPNConfig


class User(Base):
    """Модель пользователя."""

    id: Mapped[int_pk]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    # Telegram-username не обязателен, изменяем и переиспользуем — уникальность
    # должна быть на telegram_id (выше), а не здесь.
    username: Mapped[str_null_true]
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
        # Приоритет строится из SUBSCRIPTION_PRIORITY (api/subscription/models.py) —
        # единого источника для всех пяти значений SubscriptionType, а не
        # перечислением вручную.
        order_by=lambda: (
            Subscription.is_active.desc(),
            case(
                *(
                    (Subscription.type == sub_type, priority)
                    for sub_type, priority in SUBSCRIPTION_PRIORITY.items()
                ),
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
    # lazy="raise" (не "selectin", как остальные связи выше) — invited_users/
    # invited_by/payments нужны только в двух явных местах (UserAdmin, которая
    # уже сама добавляет selectinload через _with_eager_options, и
    # UserService.get_user_with_referrals), а не на каждой загрузке User,
    # в том числе на каждом HTTP-запросе через AuthMiddleware (см. #243).
    # "raise" выбран вместо "select" осознанно: пропущенное место, которому
    # на самом деле нужна связь, сразу падает явной ошибкой в тестах, а не
    # тихо открывает N+1 запрос в рантайме.
    invited_users: Mapped[list["Referral"]] = relationship(
        "Referral",
        foreign_keys=[Referral.inviter_id],
        back_populates="inviter",
        lazy="raise",
        passive_deletes=True,
    )

    invited_by: Mapped["Referral | None"] = relationship(
        "Referral",
        foreign_keys=[Referral.invited_id],
        back_populates="invited",
        uselist=False,
        lazy="raise",
        passive_deletes=True,
    )
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        foreign_keys="PaymentTransaction.user_id",
        back_populates="user",
        lazy="raise",
        order_by="PaymentTransaction.created_at.desc()",
        passive_deletes=True,
    )

    def __str__(self) -> str:
        """Строковое представление пользователя."""
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
        """Количество VPN-конфигов пользователя."""
        return len(self.vpn_configs)

    @vpn_files_count.expression  # type: ignore[no-redef]
    def vpn_files_count(cls) -> ScalarSelect[Any]:
        """SQL-выражение COUNT(VPNConfig.id) для сортировки и фильтрации без загрузки связей."""
        return (
            select(func.count(VPNConfig.id))
            .where(VPNConfig.user_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def payments_count(self) -> int:
        """Количество платёжных транзакций пользователя."""
        return len(self.payments)

    @payments_count.expression  # type: ignore[no-redef]
    def payments_count(cls) -> ScalarSelect[Any]:
        """SQL-выражение COUNT(PaymentTransaction.id) для сортировки и фильтрации без загрузки связей."""
        return (
            select(func.count(PaymentTransaction.id))
            .where(PaymentTransaction.user_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def referrals_count(self) -> int:
        """Количество приглашённых пользователей."""
        return len(self.invited_users) if self.invited_users else 0

    @referrals_count.expression  # type: ignore[no-redef]
    def referrals_count(cls) -> ScalarSelect[Any]:
        """SQL-выражение для подсчёта рефералов."""
        return (
            select(func.count(Referral.id))
            .where(Referral.inviter_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def paid_referrals_count(self) -> int:
        """Количество рефералов, получивших бонус."""
        if not self.invited_users:
            return 0

        return sum(1 for ref in self.invited_users if ref.bonus_given)

    @paid_referrals_count.expression  # type: ignore[no-redef]
    def paid_referrals_count(cls) -> ScalarSelect[int]:
        """SQL-выражение для подсчёта рефералов с бонусом."""
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
    """Модель роли пользователя."""

    id: Mapped[int_pk]
    name: Mapped[str_uniq]
    description: Mapped[str_null_true]

    users: Mapped[list["User"]] = relationship(
        "User", back_populates="role", lazy="selectin"
    )

    def __str__(self) -> str:
        """Строковое представление роли."""
        return f"{self.name} - {self.description}"

    @property
    def users_count(self) -> int:
        """Количество пользователей роли."""
        return len(self.users) if self.users else 0
