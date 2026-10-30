from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, int_pk
from shared.enums.promo_enum import PromoDiscountType

if TYPE_CHECKING:
    from api.payment.model import PaymentTransaction
    from api.users.models import User


class PromoCode(Base):
    """Промокод на скидку при оформлении подписки.

    Attributes
        id (int): Уникальный идентификатор промокода.
        code (str): Код, который вводит пользователь (хранится в верхнем
            регистре — сравнение регистронезависимое на уровне сервиса).
        discount_type (PromoDiscountType): Тип скидки — процент или
            фиксированная сумма.
        discount_value (int): Величина скидки: 1-100 для процента,
            сумма в рублях для фиксированной скидки.
        max_uses (int | None): Максимальное количество применений кода.
            None — без ограничения.
        used_count (int): Счётчик успешных применений (инкрементируется
            только при подтверждённой оплате, см. `PaymentService.
            _redeem_promo_usage`).
        valid_from (datetime | None): Начало срока действия. None — без
            ограничения.
        valid_until (datetime | None): Конец срока действия. None — без
            ограничения.
        is_active (bool): Ручной рубильник администратора — позволяет
            отключить код без удаления истории применений.
        usages (list[PromoCodeUsage]): Применения этого промокода.

    """

    id: Mapped[int_pk]
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    discount_type: Mapped[PromoDiscountType] = mapped_column(SQLEnum(PromoDiscountType))
    discount_value: Mapped[int] = mapped_column(Integer)

    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )

    usages: Mapped[list["PromoCodeUsage"]] = relationship(
        "PromoCodeUsage",
        back_populates="promo_code",
        lazy="raise",
        order_by="PromoCodeUsage.used_at.desc()",
    )

    def __str__(self) -> str:
        """Возвращает краткое строковое представление промокода."""
        limit = self.max_uses if self.max_uses is not None else "∞"
        return f"{self.code} ({self.used_count}/{limit})"


class PromoCodeUsage(Base):
    """Факт применения промокода пользователем к конкретной транзакции.

    Уникальность пары (promo_code_id, user_id) — основная защита от
    повторного применения одного и того же кода одним пользователем.

    Attributes
        id (int): Уникальный идентификатор записи.
        promo_code_id (int): Применённый промокод.
        user_id (int | None): Пользователь, применивший код.
        transaction_id (UUID): Транзакция, к которой применён код
            (один промокод на одну транзакцию).
        discount_amount (int): Сумма скидки в рублях, фактически
            предоставленная по этому применению.
        used_at (datetime): Дата и время подтверждённого применения.

    """

    id: Mapped[int_pk]

    promo_code_id: Mapped[int] = mapped_column(
        ForeignKey("promocodes.id", ondelete="CASCADE"), index=True
    )
    promo_code: Mapped["PromoCode"] = relationship(
        "PromoCode", back_populates="usages", lazy="selectin"
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[user_id], lazy="selectin", passive_deletes=True
    )

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("paymenttransactions.id", ondelete="CASCADE"),
        unique=True,
    )
    transaction: Mapped["PaymentTransaction"] = relationship(
        "PaymentTransaction", lazy="raise"
    )

    discount_amount: Mapped[int] = mapped_column(Integer)

    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("promo_code_id", "user_id", name="uq_promo_usage_user"),
    )

    def __str__(self) -> str:
        """Возвращает краткое строковое представление применения промокода."""
        return (
            f"{self.promo_code.code} -> user_id={self.user_id} "
            f"(-{self.discount_amount})"
        )
