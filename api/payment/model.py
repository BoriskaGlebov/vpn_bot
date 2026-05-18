from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import uuid4, UUID

from sqlalchemy import Enum as SQLEnum, ForeignKey, String, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base

if TYPE_CHECKING:
    from api.users.models import User


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class PaymentSource(str, Enum):
    MANUAL = "MANUAL"  # админ подтвердил
    GATEWAY = "GATEWAY"  # платежная система


# TODO Документация тесты типы данных
#  и удалить лишние комментарии
class PaymentTransaction(Base):
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    # USER
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user: Mapped["User"] = relationship("User",
                                        foreign_keys=[user_id],
                                        lazy="selectin")

    amount: Mapped[int] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    status: Mapped[PaymentStatus] = mapped_column(
        SQLEnum(PaymentStatus),
        default=PaymentStatus.PENDING,
        index=True,
    )

    source: Mapped[PaymentSource] = mapped_column(SQLEnum(PaymentSource),
                                                  default=PaymentSource.MANUAL)

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
    gateway_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __str__(self) -> str:
        short_id = str(self.id)[:4].upper()
        return f"#{short_id} {self.status.value} {self.amount}{self.currency} ({self.source.value})"