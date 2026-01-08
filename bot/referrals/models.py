import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.database import Base, int_pk

if TYPE_CHECKING:
    from bot.users.models import User


class Referral(Base):
    """Модель реферальной записи пользователя.

    Каждая запись отражает факт приглашения одного пользователя другим и
    информацию о начислении бонуса.

    Attributes
        id (int): Уникальный идентификатор записи.
        inviter_id (int): ID пользователя, который пригласил другого пользователя.
        invited_id (int): ID пользователя, который был приглашен.
        bonus_given (bool): Флаг, был ли начислен бонус за приглашение.
            По умолчанию False.
        bonus_given_at (Optional[datetime.datetime]): Дата и время начисления бонуса.
            None, если бонус еще не был начислен.
        inviter (User): Связанный объект пользователя-пригласителя.
        invited (User): Связанный объект приглашенного пользователя.

    Table constraints:
        UniqueConstraint("invited_id"): Гарантирует, что один пользователь может быть приглашен
            только один раз.

    """

    id: Mapped[int_pk]
    inviter_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invited_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    bonus_given: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    bonus_given_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    inviter: Mapped["User"] = relationship(
        "User",
        foreign_keys=[inviter_id],
        lazy="selectin",
    )

    invited: Mapped["User"] = relationship(
        "User",
        foreign_keys=[invited_id],
        lazy="selectin",
    )
    __table_args__ = (UniqueConstraint("invited_id", name="uq_referrals_invited"),)
