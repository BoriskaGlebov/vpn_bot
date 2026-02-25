from enum import Enum


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
        AMNEZIA_VPN: Кнопка получения конфигурации AmneziaVPN.
        AMNEZIA_WG: Кнопка получения конфигурации AmneziaWG.
        AMNEZIA_PROXY: Кнопка получения ссылки для подключения к прокси телеграмм.
        RENEW_SUBSCRIPTION: Кнопка продления активной подписки.
        CHOOSE_SUBSCRIPTION: Кнопка выбора и оформления подписки.
        CHECK_STATUS: Кнопка проверки статуса текущей подписки.
        HELP: Кнопка вызова справки и помощи по настройке VPN.
        ADMIN_PANEL: Кнопка перехода в административную панель (доступна администраторам).

    """

    AMNEZIA_VPN = "🔑 AmneziaVPN"
    AMNEZIA_WG = "🌐 AmneziaWG"
    AMNEZIA_PROXY = "🛡️ AmneziaProxy"
    RENEW_SUBSCRIPTION = "💎 Продлить VPN-Boriska"
    CHOOSE_SUBSCRIPTION = "💰 Выбрать подписку VPN-Boriska"
    CHECK_STATUS = "📈 Проверить статус подписки"
    HELP = "❓ Помощь в настройке VPN"
    ADMIN_PANEL = "⚙️ Панель администратора"
