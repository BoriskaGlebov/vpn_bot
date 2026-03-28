from dataclasses import dataclass

from bot.core.config import settings_bot
from bot.subscription.adapter import (
    SubscriptionAPIAdapter,
)
from shared.enums.admin_enum import RoleEnum
from shared.schemas.subscription import SSubscriptionCheck
from shared.schemas.users import SUserOut

m_subscription_local = settings_bot.messages.modes.subscription


@dataclass
class SubscriptionStats:
    """Агрегатор статистики проверки подписок.

    Класс используется для накопления и агрегации статистики как на уровне
    одного пользователя, так и для итоговой статистики по всем пользователям.

    Attributes
        checked: Количество обработанных пользователей.
        expired: Количество подписок, переведённых в истёкшие.
        notified: Количество отправленных уведомлений (пользователям и администраторам).
        configs_deleted: Количество удалённых VPN-конфигов.

    """

    checked: int = 0
    expired: int = 0
    notified: int = 0
    configs_deleted: int = 0

    def add(self, other: "SubscriptionStats") -> None:
        """Добавляет значения счётчиков из другого объекта статистики.

        Метод выполняет покомпонентное суммирование счётчиков и используется
        для агрегации статистики от отдельных обработчиков или пользователей.

        Args:
            other: Экземпляр `SubscriptionStats`, значения которого будут
                добавлены к текущему объекту.

        Returns
            None

        """
        self.expired += other.expired
        self.notified += other.notified
        self.configs_deleted += other.configs_deleted


class SubscriptionService:
    """Сервис для бизнес-логики подписки."""

    def __init__(self, adapter: SubscriptionAPIAdapter) -> None:
        self.api_adapter = adapter

    async def check_premium(self, tg_id: int) -> tuple[bool, RoleEnum, bool]:
        """Проверяет, имеет ли пользователь активную премиум-подписку.

        Args:
            tg_id (int): Telegram ID пользователя.

        Returns
            tuple[bool, str, bool]: Кортеж из трёх значений:
                - bool: True, если у пользователя премиум-подписка, иначе False.
                - RoleEnum: Роль пользователя (например, "founder", "user" и т.д.).
                - bool: True, если подписка активна, иначе False.

        Raises
            UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

        """
        data = await self.api_adapter.check_premium(tg_id=tg_id)
        check = SSubscriptionCheck.model_validate(data)
        return check.premium, check.role, check.is_active

    async def start_trial_subscription(self, tg_id: int, days: int) -> None:
        """Активирует пробный период подписки для пользователя.

        Метод проверяет, есть ли у пользователя активная подписка и не использовал ли он
        пробный период ранее. Если пробный период уже использован или есть активная
        подписка, будет выброшено исключение `ValueError`.

        Args:
            tg_id (int): Telegram ID пользователя.
            days (int): Количество дней пробного периода.

        Raises
            ValueError: Если у пользователя уже есть активная подписка или пробный
                период уже использован.

        """
        res, status = await self.api_adapter.activate_trial(tg_id=tg_id, days=days)
        # if status != 201:
        #     raise ValueError(res.get("detail", "Уже есть подписка."))

    async def activate_paid_subscription(
        self, tg_id: int, months: int, premium: bool
    ) -> SUserOut | None:
        """Активирует платную подписку после подтверждения оплаты.

        Метод проверяет наличие пользователя и активной подписки указанного типа.
        Если подписка уже активна, продлевает её. Для основателя (`FOUNDER`)
        всегда продлевается текущая подписка и устанавливается тип `PREMIUM`.
        В противном случае создается новая подписка через DAO.

        Args:
            tg_id (int): Telegram ID пользователя.
            months (int): Количество месяцев для продления или новой подписки.
            premium (bool): Флаг, указывающий на тип подписки (`PREMIUM` или `STANDARD`).

        Returns
            Optional[SUserOut]: Объект пользователя в формате схемы, либо `None`, если
                пользователь не найден (в реальности выбрасывается `UserNotFoundError`).

        Raises
            UserNotFoundError: Если пользователь с указанным `user_id` не найден.

        """
        res = await self.api_adapter.activate_paid(
            tg_id=tg_id, months=months, premium=premium
        )
        return res
