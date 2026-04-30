from bot.core.config import settings_bot
from bot.subscription.enums import ToggleSubscriptionMode


def get_correct_price_map(premium: bool, founder: bool) -> dict[int, int]:
    """Возвращает актуальную карту тарифов в зависимости от типа пользователя.

    Определяет, какую ценовую матрицу использовать для расчёта стоимости подписки:
    - Premium пользователи получают премиум-ценовую матрицу.
    - Founder пользователи получают специальную founder-ценовую матрицу.
    - Обычные пользователи получают стандартную ценовую матрицу.

    Args:
        premium (bool): Флаг, указывающий, что пользователь имеет премиум-статус.
        founder (bool): Флаг, указывающий, что пользователь имеет статус основателя (founder).

    Returns
        Dict[int, int]: Словарь, где ключ — срок подписки в месяцах,
        значение — стоимость в виде числа.

    Notes
        Приоритет выбора:
        1. premium
        2. founder
        3. standard

        Если одновременно переданы premium=True и founder=True,
        будет использована premium-матрица.

    """
    if premium:
        return settings_bot.price_map_premium
    elif founder:
        return settings_bot.price_map_founder
    else:
        return settings_bot.price_map


def get_correct_sub_type(premium: bool, founder: bool) -> str:
    """Определяет тип подписки пользователя.

    Функция возвращает строковое представление типа подписки
    на основе переданных флагов статуса пользователя.

    Приоритет определения типа подписки:
    1. premium
    2. founder
    3. standard

    Args:
        premium (bool): Флаг премиум-статуса пользователя.
        founder (bool): Флаг статуса основателя (founder).

    Returns
        str: Тип подписки в верхнем регистре. Возможные значения:
        - PREMIUM
        - FOUNDER
        - STANDARD

    Notes
        Если одновременно переданы premium=True и founder=True,
        будет выбран тип PREMIUM как имеющий более высокий приоритет.

    """
    if premium:
        return ToggleSubscriptionMode.PREMIUM.upper()
    elif founder:
        return ToggleSubscriptionMode.FOUNDER.upper()
    else:
        return ToggleSubscriptionMode.STANDARD.upper()
