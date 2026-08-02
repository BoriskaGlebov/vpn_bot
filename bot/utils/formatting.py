from datetime import datetime

from aiogram.types import User


def format_username(user: User | None) -> str:
    """Возвращает читаемое отображаемое имя пользователя Telegram.

    Args:
        user (User | None): Пользователь Telegram или None.

    Returns
        str: "@username", либо полное имя/"Гость_{id}" если username не задан,
        либо "Гость" если пользователь неизвестен.

    """
    if user is None:
        return "Гость"
    if user.username:
        return f"@{user.username}"
    return user.full_name or f"Гость_{user.id}"


def format_subscription_end_date(end_date: datetime | None) -> str:
    """Форматирует дату окончания подписки для показа пользователю.

    Args:
        end_date (datetime | None): Дата окончания подписки.

    Returns
        str: Дата в формате YYYY-MM-DD, либо "бессрочно", если не задана.

    """
    return end_date.strftime("%Y-%m-%d") if end_date else "бессрочно"
