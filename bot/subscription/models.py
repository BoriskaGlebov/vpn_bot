import datetime
from enum import Enum
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.config import logger, settings_bot
from bot.database import Base, int_pk

if TYPE_CHECKING:
    from users.models import User


# TODO Есть проблема с продлением подписки.
# Пользователь берет подписку по дешевле на большой срок,
# потом покупает прем на маленький и теперь у него
# прем на весь срок всех его подписок. Возможно это можно решить если сделать, что б связь была не один к одному,а один ко многим


class SubscriptionType(str, Enum):
    """Типы подписок пользователей.

    Attributes
        TRIAL (str): Пробная подписка с ограниченным сроком действия.
        STANDARD (str): Стандартная подписка с базовыми возможностями.
        PREMIUM (str): Премиум-подписка с расширенным функционалом.

    """

    TRIAL = "trial"
    STANDARD = "standard"
    PREMIUM = "premium"


DEVICE_LIMITS = {
    SubscriptionType.TRIAL: 1,
    SubscriptionType.STANDARD: settings_bot.MAX_CONFIGS_PER_USER,
    SubscriptionType.PREMIUM: settings_bot.MAX_CONFIGS_PER_USER * 2,
}


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
        type: (SubscriptionType): Тип подписки TRIAL, STANDARD, PREMIUM.

    """

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(default=False)
    type: Mapped[SubscriptionType] = mapped_column(
        SQLEnum(SubscriptionType, name="subscription_type"), default=None, nullable=True
    )
    start_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    end_date: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="subscription")

    def __str__(self) -> str:
        """Строковое представление."""
        status = "Активна" if self.is_active else "Неактивна"
        stat_type = self.type.value.upper() if self.type else ""
        until = (
            self.end_date.strftime("%Y-%m-%d %H:%M") if self.end_date else "бессрочная"
        )
        return f"{status} {stat_type} (до {until})"

    def activate(
        self,
        days: int | None = None,
        month_num: int | None = None,
        sub_type: SubscriptionType = SubscriptionType.STANDARD,
    ) -> None:
        """Активирует подписку на указанное количество дней или месяцев.

        Args:
            sub_type (SubscriptionType): Тип подписки пользователя, по умолчанию Стандарт
            days (int|None): Количество дней на подписку
            month_num (int|None): Количество месяцев на подписку

        """
        if sub_type == SubscriptionType.TRIAL:
            if self.user.has_used_trial:
                raise ValueError("Пользователь уже использовал триал-подписку")
            self.user.has_used_trial = True
        self.type = sub_type
        self.is_active = True
        self.start_date = datetime.datetime.now(tz=datetime.UTC)

        # если указаны дни → добавляем дни
        if days is not None:
            self.end_date = self.start_date + datetime.timedelta(days=days)
        # если указаны месяцы → добавляем месяцы
        elif month_num is not None:
            self.end_date = self.start_date + relativedelta(months=month_num)
        else:
            raise ValueError("Нужно указать либо days, либо month_num")

        logger.info(
            f"[DAO] Активирована подписка с {self.start_date} до {self.end_date}"
        )

    def extend(self, days: int = 0, months: int = 0) -> None:
        """Продлевает подписку на указанное количество дней или месяцев.

        Args:
            days (int): Количество дней для продления.
            months (int): Количество месяцев для продления.

        """
        if not self.end_date or self.end_date < datetime.datetime.now(datetime.UTC):
            # если подписка бессрочная или уже истекла → начинаем с текущей даты
            new_start = datetime.datetime.now(datetime.UTC)
        else:
            # если подписка активна → начинаем с текущей даты окончания
            new_start = self.end_date

        new_end = (
            new_start + datetime.timedelta(days=days) + relativedelta(months=months)
        )
        self.end_date = new_end
        self.is_active = True

        logger.info(f"[DAO] Подписка продлена до {self.end_date}")

    def deactivate(self) -> None:
        """Деактивирует подписку."""
        self.is_active = False
        self.end_date = datetime.datetime.now(tz=datetime.UTC)

    def is_expired(self) -> bool:
        """Проверяет, истекла ли подписка.

        Returns
            bool: True, если срок подписки истёк или она неактивна.

        """
        if not self.is_active:
            return True
        return self.end_date and datetime.datetime.now(datetime.UTC) > self.end_date

    def remaining_days(self) -> int | None:
        """Возвращает количество оставшихся дней до окончания.

        Returns
            int | None: Количество дней или None, если подписка бессрочная.

        """
        if not self.end_date:
            return None
        delta = self.end_date - datetime.datetime.now(tz=datetime.UTC)
        return max(delta.days, 0)


if __name__ == "__main__":
    print(SubscriptionType.PREMIUM.value)
