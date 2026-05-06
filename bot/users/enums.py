from enum import Enum, StrEnum
from pprint import pprint

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
        RENEW_SUBSCRIPTION: Кнопка продления активной подписки.
        CHOOSE_SUBSCRIPTION: Кнопка выбора и оформления подписки.
        CHECK_STATUS: Кнопка проверки статуса текущей подписки.
        HELP: Кнопка вызова справки и помощи по настройке VPN.
        ADMIN_PANEL: Кнопка перехода в административную панель (доступна администраторам).
        PREMIUM: Возможности премиум пользователей.

    """

    AMNEZIA_PROXY = "📦 AmneziaProxy"
    FREE_AMNEZIA_PROXY = "📦 Free AmneziaProxy TG"
    RENEW_SUBSCRIPTION = "💎 Продлить VPN-Boriska"
    CHOOSE_SUBSCRIPTION = "💰 Выбрать подписку VPN-Boriska"
    CHECK_STATUS = "📈 Проверить статус подписки"
    HELP = "❓ Помощь в настройке VPN"
    ADMIN_PANEL = "⚙️ Панель администратора"
    PREMIUM = "💎 Мой Премиум"


class Location(str, Enum):
    """Перечисление доступных VPN-локаций.

    Используется для идентификации серверов VPN по географическому признаку
    и сопоставления с конфигурацией из settings_bot.

    Attributes
        MAIN (str): основная VPN-локация (значение берётся из settings_bot.vpn.main).
        FINLAND (str): финская VPN-локация (settings_bot.vpn.fi).
        SOFIA (str): софийская VPN-локация (settings_bot.vpn.sof).

    """

    MAIN = settings_bot.vpn.main.location_prefix.lower()
    # FRANCE = "FR"
    FINLAND = settings_bot.vpn.fi.location_prefix.lower()


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

        XRAY: Протокол Xray (VLESS + Reality + XHTTP/TLS).
            Используется для маскировки трафика под обычный HTTPS
            и обхода сетевых ограничений.

    """

    AWG = "AmneziaWG"
    AVPN = "AmneziaVPN"
    XRAY = "X-RAY Vless Reality XHTTP/TLS"


if __name__ == "__main__":
    pprint(settings_bot.vpn.model_dump())
    # print(settings_bot.vpn.main.location_prefix.lower())
    # print(settings_bot.vpn.fi.location_prefix.lower())
    # print(settings_bot.vpn.nodes)
    # for loc in Location:
    # print(loc.name.lower())
    # print(loc.name==Location.MAIN.name)
    # print(settings_bot.vpn.main.xray)
    # if loc.name==Location.MAIN.name:
    #     print(settings_bot.vpn.nodes.get(loc.name.lower()))
    # else:
    #     print(settings_bot.vpn.nodes.get(loc.value))
    # print(settings_bot.vpn.nodes.get("fi"))
    # print(settings_bot.vpn.nodes.get("main"))
