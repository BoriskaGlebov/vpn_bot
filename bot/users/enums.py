from enum import Enum, StrEnum

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
        AMNEZIA_PROXY: Кнопка получения ссылки для подключения к прокси телеграмм.
        FREE_AMNEZIA_PROXY: Кнопка получения ссылки для подключения к прокси телеграмм бесплатно.
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

    # FIXME  убираю кнопку с прокси, что б людей не путать
    AMNEZIA_PROXY = "📦 AmneziaProxy"
    # FIXME  убираю кнопку с прокси, что б людей не путать
    FREE_AMNEZIA_PROXY = "📦 Free AmneziaProxy TG"
    MY_SUBSCRIPTION = "💳 Моя подписка"
    GET_SUBSCRIPTION = "🎁 Оформить подписку"
    HELP = "❓ Помощь в настройке VPN"
    ADMIN_PANEL = "⚙️ Панель администратора"
    PREMIUM = "💎 Премиум возможности 💎"
    BACK = "❌ Стандартные локации"
    INFO = "📝 Информация о проекте"


class Location(str, Enum):
    """Перечисление доступных VPN-локаций.

    Используется для идентификации серверов VPN по географическому признаку
    и сопоставления с конфигурацией из settings_bot.

    Attributes
        MAIN (str): основная VPN-локация (значение берётся из settings_bot.vpn.main).
        FINLAND (str): финская VPN-локация (settings_bot.vpn.fi).
        SOFIA (str): софийская VPN-локация (settings_bot.vpn.sof).
        WAW (str): варшавская VPN-локация (settings_bot.vpn.waw).

    """

    MAIN = settings_bot.vpn.main.location_prefix.lower()
    FINLAND = (
        settings_bot.vpn.fi.location_prefix.lower()
        if settings_bot.vpn.fi is not None
        else "fi"
    )
    WAW = (
        settings_bot.vpn.waw.location_prefix.lower()
        if settings_bot.vpn.waw is not None
        else "waw"
    )


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
    configured_prefixes = {
        node.location_prefix.lower() for node in settings_bot.vpn.nodes.values()
    }
    return [loc for loc in Location if loc.value in configured_prefixes]


class PremiumLocation(str, Enum):
    """Перечисление доступных премиум VPN-локаций.

    Используется для идентификации серверов VPN по географическому признаку
    и сопоставления с конфигурацией из settings_bot.

    Attributes
        SOFIA (str): софийская VPN-локация (settings_bot.vpn.sof).

    """

    SOFIA = settings_bot.vpn.sof.location_prefix.lower()


class VPNProtocol(StrEnum):
    """Поддерживаемые VPN-протоколы.

    Значения перечисления используются для отображения пользователю
    и конфигурации подключений.

    Attributes
        AWG: Протокол Amnezia WireGuard (AmneziaWG).
            Оптимизированная версия WireGuard с обходом DPI.

        AVPN: Протокол AmneziaVPN.
            Собственная реализация VPN с дополнительной обфускацией трафика.

        AMNEZIA: Протокол Amnezia WireGuard.

        XRAY: Протокол Xray (VLESS + Reality + XHTTP/TLS).
            Используется для маскировки трафика под обычный HTTPS
            и обхода сетевых ограничений.

    """

    # AWG = "AmneziaWG"
    # AVPN = "AmneziaVPN"
    AMNEZIA = "AmneziaVPN"
    XRAY = "⚡ XRay Pro"
