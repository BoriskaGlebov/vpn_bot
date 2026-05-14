from enum import Enum


class SubscriptionEventType(str, Enum):
    """Типы событий, используемых в системе подписок.

    Эти значения применяются для маршрутизации и обработки доменных событий,
    связанных с пользователями и их подписками.

    Attributes
        USER_NOTIFY: Событие пользовательского уведомления.
        ADMIN_NOTIFY: Событие уведомления администратора.
        DELETE_VPN_CONFIGS: Событие удаления VPN конфигураций пользователя.
        DELETE_PROXY: Событие удаления proxy конфигураций пользователя.

    """

    USER_NOTIFY = "user_notify"
    ADMIN_NOTIFY = "admin_notify"
    DELETE_VPN_CONFIGS = "delete_vpn_configs"
    DELETE_PROXY = "delete_proxy"


class DeleteStatus(Enum):
    """Статусы результата удаления сущности.

    Используется для унификации результата операций удаления,
    например при работе с конфигурациями, пользователями или ресурсами.

    Attributes
        DELETED (str): Объект найден и успешно удалён.
        NOT_FOUND (str): Объект не найден ни в одном источнике.
        ERROR (str): Произошла ошибка при проверке или удалении.

    """

    DELETED = "deleted"
    NOT_FOUND = "not_found"
    ERROR = "error"
