import datetime
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.config import logger
from bot.database import Base, int_pk

if TYPE_CHECKING:
    from users.models import User


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

    """

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    is_active: Mapped[bool] = mapped_column(default=False)
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
        until = (
            self.end_date.strftime("%Y-%m-%d %H:%M") if self.end_date else "бессрочная"
        )
        return f"{status} (до {until})"

    def activate(self, days: int | None = None, month_num: int | None = None) -> None:
        """Активирует подписку на указанное количество дней или месяцев.

        Args:
            days (int|None): Количество дней на подписку
            month_num (int|None): Количество месяцев на подписку

        """
        self.is_active = True
        self.start_date = datetime.datetime.now()

        # если указаны дни → добавляем дни
        if days is not None:
            self.end_date = self.start_date + datetime.timedelta(days=days)
        # если указаны месяцы → добавляем месяцы
        elif month_num is not None:
            self.end_date = self.start_date + relativedelta(months=month_num)
        else:
            raise ValueError("Нужно указать либо days, либо month_num")

        logger.info(f"Активирована подписка с {self.start_date} до {self.end_date}")

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

        logger.info(f"Подписка продлена до {self.end_date}")

    def deactivate(self) -> None:
        """Деактивирует подписку."""
        self.is_active = False
        self.end_date = datetime.datetime.now()

    def is_expired(self) -> bool:
        """Проверяет, истекла ли подписка.

        Returns
            bool: True, если срок подписки истёк или она неактивна.

        """
        if not self.is_active:
            return True
        if self.end_date and datetime.datetime.now() > self.end_date:
            return True
        return False

    def remaining_days(self) -> int | None:
        """Возвращает количество оставшихся дней до окончания.

        Returns
            int | None: Количество дней или None, если подписка бессрочная.

        """
        if not self.end_date:
            return None
        delta = self.end_date - datetime.datetime.now()
        return max(delta.days, 0)
