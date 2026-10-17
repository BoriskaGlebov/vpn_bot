import datetime
import math
from enum import Enum
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from loguru import logger
from sqlalchemy import DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.app_error.base_error import AppError
from api.core.config import settings_api
from api.core.database import Base, int_pk

if TYPE_CHECKING:
    from api.users.models import User


class SubscriptionType(str, Enum):
    """Типы подписок пользователей.

    Attributes
        TRIAL (str): Пробная подписка с ограниченным сроком действия.
        STANDARD (str): Стандартная подписка с базовыми возможностями.
        PREMIUM (str): Премиум-подписка с расширенным функционалом.
        FOUNDER (str): Подписка для основателей с расширенным функционалом.
        ULTIMATE (str): Премиум-подписка с отключением ограничений на количество устройств.


    """

    TRIAL = "trial"
    STANDARD = "standard"
    PREMIUM = "premium"
    FOUNDER = "founder"
    ULTIMATE = "ultimate"


# #277: приоритет подписки при сортировке User.subscriptions — единый источник,
# из которого строится case() в api/users/models.py. Любое значение SubscriptionType,
# не попавшее в этот словарь, ловится тестом (перебор enum), а не тихим else_=0.
SUBSCRIPTION_PRIORITY: dict[SubscriptionType, int] = {
    SubscriptionType.TRIAL: 1,
    SubscriptionType.STANDARD: 2,
    SubscriptionType.PREMIUM: 3,
    SubscriptionType.FOUNDER: 4,
    SubscriptionType.ULTIMATE: 5,
}

# Практический "безлимит" для ULTIMATE: VPNConfigDAO.get_limit_status сравнивает
# current < limit, поэтому ноль или отсутствие ключа означает "лимит 0", а не
# "без ограничений" — такое значение-сигнал должно быть явно большим, а не None.
DEVICE_LIMIT_UNLIMITED = 10_000

DEVICE_LIMITS: dict[SubscriptionType, int] = {
    SubscriptionType.TRIAL: 1,
    SubscriptionType.STANDARD: settings_api.core.max_configs_per_user,
    SubscriptionType.PREMIUM: int(settings_api.core.max_configs_per_user * 2),
    SubscriptionType.FOUNDER: int(settings_api.core.max_configs_per_user * 2),
    SubscriptionType.ULTIMATE: DEVICE_LIMIT_UNLIMITED,
}


class Subscription(Base):
    """Модель подписки пользователя.

    Хранит статус, дату начала и окончания действия подписки.
    Связана с пользователем отношением один-ко-многим (с миграции
    `6a0357aa804b`) — у пользователя может быть несколько записей
    подписки (история), активна из них обычно одна.

    Attributes
        id (int): Уникальный идентификатор записи.
        user_id (int): Внешний ключ на пользователя.
        is_active (bool): Флаг активности подписки.
        start_date (datetime): Дата начала подписки.
        end_date (datetime | None): Дата окончания подписки (None — бессрочная).
        user (User): Пользователь, владелец подписки.
        type (SubscriptionType | None): Тип подписки; None до первого
            activate() (запись только создана, ещё не активирована).

    """

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    is_active: Mapped[bool] = mapped_column(default=False)
    # Optional: до вызова activate() у только что созданной записи (см.
    # SubscriptionDAO.activate_subscription) тип не задан — аннотация без
    # None противоречила бы nullable=True и фактическому поведению кода,
    # который везде защищается `subscription.type.value if subscription.type
    # else None` (#283).
    type: Mapped[SubscriptionType | None] = mapped_column(
        SQLEnum(SubscriptionType, name="subscription_type"), default=None, nullable=True
    )
    start_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    end_date: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions", lazy="selectin")

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

        Правило «пробный период даётся один раз» (`User.has_used_trial`)
        здесь не проверяется и не выставляется — это бизнес-правило живёт
        в `SubscriptionService.start_trial_subscription`, а не в модели
        подписки: иначе метод модели менял бы соседнюю сущность (`User`),
        дублируя проверку с сервисом (см. #283, тот же класс, что #244).

        Args:
            sub_type (SubscriptionType): Тип подписки пользователя, по умолчанию Стандарт
            days (int|None): Количество дней на подписку
            month_num (int|None): Количество месяцев на подписку

        """
        now = datetime.datetime.now(tz=datetime.UTC)
        self.type = sub_type
        self.is_active = True
        self.start_date = now
        # если указаны дни → добавляем дни
        if days is not None:
            self.end_date = now + datetime.timedelta(days=days)
        # если указаны месяцы → добавляем месяцы
        elif month_num is not None:
            self.end_date = self.start_date + relativedelta(months=month_num)
        else:
            raise AppError(message="Нужно указать либо days, либо month_num")

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
        return bool(
            self.end_date and datetime.datetime.now(datetime.UTC) > self.end_date
        )

    def remaining_days(self) -> int | None:
        """Возвращает количество оставшихся дней до окончания, округляя вверх.

        `timedelta.days` отбрасывает дробную часть, поэтому при остатке
        меньше суток (но больше нуля) показывал бы «0 дней» у подписки,
        которая на самом деле ещё действует (см. #282, тот же источник
        дефекта, что у #266 в выдаче XRay-конфигов). Для отображения
        остаток меньше суток округляется вверх до 1 — на is_expired()
        (сравнение по точному времени) это не влияет.

        Returns
            int | None: Количество дней (не меньше 1 при остатке > 0, иначе
                0) или None, если подписка бессрочная.

        """
        if not self.end_date:
            return None
        delta_seconds = (
            self.end_date - datetime.datetime.now(tz=datetime.UTC)
        ).total_seconds()
        if delta_seconds <= 0:
            return 0
        return math.ceil(delta_seconds / 86400)
