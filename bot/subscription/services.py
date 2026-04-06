from dataclasses import dataclass

from bot.app_error.api_error import APIClientError
from bot.core.config import settings_bot
from bot.subscription.adapter import (
    SubscriptionAPIAdapter,
)
from bot.subscription.schemas import SSubscriptionCheck
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum

m_subscription_local = settings_bot.messages.modes.subscription


# TODO Мне кажется это я еще не тестировал


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

    def __init__(
        self, adapter: SubscriptionAPIAdapter, user_adapter: UsersAPIAdapter
    ) -> None:
        self.api_adapter = adapter
        self.user_adapter = user_adapter

    async def check_premium(self, tg_id: int) -> tuple[bool, RoleEnum, bool, bool]:
        """Проверяет, имеет ли пользователь активную премиум-подписку.

        Args:
            tg_id (int): Telegram ID пользователя.

        Returns
            tuple[bool, str, bool]: Кортеж из трёх значений:
                - bool: True, если у пользователя премиум-подписка, иначе False.
                - RoleEnum: Роль пользователя (например, "founder", "user" и т.д.).
                - bool: True, если подписка активна, иначе False.
                - bool: Использовал ли триал.

        Raises
            UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

        """
        data = await self.api_adapter.check_premium(tg_id=tg_id)
        check = SSubscriptionCheck.model_validate(data)
        return check.premium, check.role, check.is_active, check.used_trial

    async def start_trial_subscription(self, tg_id: int, days: int) -> None:
        """Активирует пробный период подписки для пользователя.

        Метод проверяет, есть ли у пользователя активная подписка и не использовал ли он
        пробный период ранее. Если пробный период уже использован или есть активная
        подписка, будет выброшено исключение `ValueError`.

        Args:
            tg_id (int): Telegram ID пользователя.
            days (int): Количество дней пробного периода.

        Raises
            APIClientError: Если у пользователя уже есть активная подписка или пробный
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
            SUserOut | None:  Объект пользователя в формате схемы, либо `None`, если
                пользователь не найден (в реальности выбрасывается `UserNotFoundError`).

        Raises
            APIClientError: Если пользователь с указанным `user_id` не найден.

        """
        res = await self.api_adapter.activate_paid(
            tg_id=tg_id, months=months, premium=premium
        )
        return res

    async def _get_referral_info(self, tg_id: int) -> str:
        """Формирует текстовую информацию о реферальной статистике пользователя.

        Args:
            tg_id (int): Telegram ID пользователя.

        Returns
            str: Отформатированная строка со статистикой рефералов.

        Raises
            APIClientError: Если произошла ошибка при получении данных (обрабатывается внутри).

        """
        try:
            referrals_data = await self.user_adapter.get_referrals(telegram_id=tg_id)
        except APIClientError:
            return "Пользователь не найден в системе рефералов."
        total = referrals_data.referrals_count
        paid = referrals_data.paid_referrals_count
        conversion = referrals_data.referral_conversion * 100  # проценты
        # TODO приглашение нормальным сделай
        if total == 0:
            return (
                "👋 Пока у вас нет приглашённых друзей.\n\n"
                "Каждое новое приглашение — это шаг к бесплатной или продлённой подписке! "
                "🎁 Приглашайте друзей и получайте бонусы, пока наслаждаетесь VPN."
            )

        return (
            f"🎉 *Ваша реферальная статистика* 🎉\n\n"
            f"👥 Всего приглашено: ***{total}***\n"
            f"💰 Получили бонус: *{paid}* месяцев\n"
            f"🚀 Конверсия: *{conversion:.2f}%*\n\n"
            f"🔥 Продолжайте приглашать друзей, чтобы увеличивать свои бонусы!\n"
            f"🎁 Чем больше приглашений — тем больше преимуществ!"
        )

    async def get_subscription_info(self, tg_id: int) -> str:
        """Возвращает информацию о подписке пользователя и его VPN-конфигах.

        Args:
            tg_id (int): ID Telegram-пользователя.

        Raises
            ValueError: Если пользователь не найден.

        Returns
            str: Текст с информацией о подписке и списком конфигов.

        """
        data = await self.api_adapter.get_subscription_info(tg_id=tg_id)

        if data.status == "no_subscription":
            return "У вас нет подписки."

        status = "✅ Активна" if data.status == "active" else "🔒 Неактивна"
        sbs_type = (
            f"<b>{data.subscription_type.upper()}</b>" if data.subscription_type else ""
        )
        end_date = (
            data.end_date.strftime("%Y-%m-%d")
            if data.end_date
            else "Бесконечность не предел"
        )

        remaining_text = f"{data.remaining} до ({end_date})"

        conf_list = "\n\n".join([f"📌 {conf.file_name}" for conf in data.configs])

        return f"{status} {sbs_type} — {remaining_text}\n\n{conf_list}"

    async def get_subscription_and_referral_info(self, tg_id: int) -> str:
        """Возвращает объединённую информацию о подписке и рефералах.

        Args:
            tg_id (int): Telegram ID пользователя.

        Returns
            str: Итоговый текст (подписка + рефералы).

        """
        subscription_info = await self.get_subscription_info(tg_id)
        referral_info = await self._get_referral_info(tg_id)
        return f"{subscription_info}\n\n{referral_info}"
