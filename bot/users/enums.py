from enum import Enum

from bot.core.config import settings_bot


class ChatType(str, Enum):
    """Типы чатов в Telegram."""

    PRIVATE = "private"


class MainMenuText(str, Enum):
    """Тексты кнопок главного меню пользователя.

    Enum содержит фиксированные текстовые значения, используемые в ReplyKeyboardMarkup
    главного меню Telegram-бота. Значения применяются:

    - при формировании клавиатур;
    - в фильтрах aiogram (F.text == ...);
    - в хендлерах пользовательских команд.


    Attributes
        MY_SUBSCRIPTION: Кнопка входа в подменю подписки при активной подписке
            (продлить + проверить статус).
        GET_SUBSCRIPTION: Кнопка входа в то же подменю, но с явным призывом к
            действию — показывается, если активной подписки нет (в том числе
            истёкшей).
        HELP: Кнопка вызова справки и помощи по настройке VPN.
        ADMIN_PANEL: Кнопка перехода в административную панель (доступна администраторам).
        PREMIUM: Возможности премиум пользователей.
        BACK: Шаг назад
        INFO: Информация по проекту для регистрации платежной системы.

    """

    MY_SUBSCRIPTION = "💳 Моя подписка"
    GET_SUBSCRIPTION = "🎁 Оформить подписку"
    HELP = "❓ Помощь в настройке VPN"
    ADMIN_PANEL = "⚙️ Панель администратора"
    PREMIUM = "💎 Премиум возможности 💎"
    BACK = "❌ Стандартные локации"
    INFO = "📝 Информация о проекте"


class Location(str, Enum):
    """Перечисление доступных VPN-локаций.

    Значение каждого члена — ключ ноды в `settings_bot.vpn.nodes`, а не
    `location_prefix` ноды. Раньше значением был `location_prefix` (напр.
    "fr" на prod при ключе ноды "main"), из-за чего `nodes.get(location.value)`
    не находил ноду вообще никогда, и реально работал только обходной путь
    по `location.name.lower()` (см. аудит, #268). Ключи — литералы, а не
    вычисление из `settings_bot` при импорте модуля: отсутствие опциональной
    ноды (`fi`, `waw`) не должно ломать импорт.

    Attributes
        MAIN (str): основная VPN-локация, ключ ноды "main".
        FINLAND (str): финская VPN-локация, ключ ноды "fi".
        WAW (str): варшавская VPN-локация, ключ ноды "waw".

    """

    MAIN = "main"
    FINLAND = "fi"
    WAW = "waw"


def available_locations() -> list["Location"]:
    """Локации, для которых реально сконфигурирована VPN-нода.

    `Location` объявлен статически (набор локаций фиксирован в коде), а
    стоящая за конкретной локацией нода может быть временно не настроена
    в app_config.toml (см. `settings_bot.vpn.fi`). Используйте эту функцию
    вместо прямого перебора `Location` везде, где для локации нужна
    реальная нода (клавиатуры, регистрация хендлеров, генерация конфигов) —
    иначе можно получить VPNNodeNotFoundError на локации-заглушке.

    Returns
        list[Location]: подмножество Location с реально сконфигурированными нодами.

    """
    return [loc for loc in Location if loc.value in settings_bot.vpn.nodes]


class PremiumLocation(str, Enum):
    """Перечисление доступных премиум VPN-локаций.

    См. `Location` — то же решение: значение — ключ ноды, а не
    `location_prefix`, и не вычисляется из `settings_bot` при импорте.

    Attributes
        SOFIA (str): софийская VPN-локация, ключ ноды "sof".

    """

    SOFIA = "sof"


def available_premium_locations() -> list["PremiumLocation"]:
    """Премиум-локации, для которых реально сконфигурирована VPN-нода.

    См. `available_locations()` — то же рассуждение для премиум-набора.
    До этой функции `sof` не был защищён так же, как `fi`/`waw`: не было
    отдельной проверки на отсутствие ноды (см. #268).

    Returns
        list[PremiumLocation]: подмножество PremiumLocation с реально
            сконфигурированными нодами.

    """
    return [loc for loc in PremiumLocation if loc.value in settings_bot.vpn.nodes]
