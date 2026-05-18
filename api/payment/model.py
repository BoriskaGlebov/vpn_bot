from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import JSON
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base

if TYPE_CHECKING:
    from api.users.models import User


class PaymentStatus(str, Enum):
    """Статус платежной транзакции."""

    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PaymentSource(str, Enum):
    """Источник создания платежа."""

    MANUAL = "MANUAL"  # админ подтвердил
    GATEWAY = "GATEWAY"  # платежная система


# TODO Документация тесты типы данных
#  и удалить лишние комментарии
class PaymentTransaction(Base):
    """Модель платежной транзакции пользователя.

    Используется для хранения информации о платежах, подписках,
    а также административных подтверждениях.

    Attributes
        id:
            Уникальный идентификатор транзакции.

        user_id:
            ID пользователя, которому принадлежит платеж.

        user:
            Связанный объект пользователя.

        amount:
            Сумма платежа в минимальных единицах валюты
            (например, копейки для RUB).

        currency:
            Код валюты в формате ISO 4217.

        status:
            Текущий статус платежа.

        source:
            Источник создания платежа.

        subscription_months:
            Количество месяцев подписки.

        is_premium:
            Флаг премиум-подписки.

        is_founder:
            Флаг founder-статуса.

        created_by_admin_id:
            ID администратора, создавшего транзакцию вручную.

        created_by_admin:
            Объект администратора, создавшего транзакцию.

        confirmed_by_admin_id:
            ID администратора, подтвердившего платеж.

        confirmed_by_admin:
            Объект администратора, подтвердившего платеж.

        gateway_transaction_id:
            ID транзакции во внешней платежной системе.

        gateway_payload:
            Сырые данные ответа платежного шлюза.

        description:
            Дополнительное описание платежа.

        confirmed_at:
            Дата и время подтверждения администратором.

        paid_at:
            Дата и время успешной оплаты.

    """

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # USER
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id], lazy="selectin")

    amount: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        index=True,
    )

    source: Mapped[PaymentSource] = mapped_column(
        SQLEnum(PaymentSource), default=PaymentSource.MANUAL
    )

    subscription_months: Mapped[int] = mapped_column(nullable=False)
    is_premium: Mapped[bool] = mapped_column(default=False)
    is_founder: Mapped[bool] = mapped_column(default=False)

    # ADMIN AUDIT
    created_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by_admin: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by_admin_id],
        lazy="selectin",
    )

    confirmed_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_by_admin: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[confirmed_by_admin_id],
        lazy="selectin",
    )

    # GATEWAY FUTURE
    gateway_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    gateway_payload: Mapped[dict[Any, Any] | None] = mapped_column(JSON, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __str__(self) -> str:
        """Возвращает краткое строковое представление транзакции.

        Returns
            Строка в формате:
            "#ABCD PAID 1000RUB (MANUAL)".

        """
        short_id = str(self.id)[:4].upper()
        return (
            f"#{short_id} "
            f"{self.status.value} "
            f"{self.amount}{self.currency} "
            f"({self.source.value})"
        )

    @property
    def tg_id(self) -> int | None:
        """Возвращает Telegram ID пользователя.

        Returns
            Telegram ID пользователя либо None,
            если пользователь не загружен.

        """
        return self.user.telegram_id if self.user else None
