from dataclasses import dataclass

from api.scheduler.enums import SubscriptionEventType


@dataclass
class BaseEvent:
    """Базовое событие системы подписок.

    Attributes
        type: Тип события, определяющий его назначение и обработку.

    """

    type: SubscriptionEventType


@dataclass
class UserNotifyEvent(BaseEvent):
    """Событие уведомления пользователя.

    Используется для отправки сообщений пользователю (например,
    при истечении подписки или скором окончании).

    Attributes
        type: Тип события (USER_NOTIFY).
        user_id: Telegram ID пользователя.
        message: Текст уведомления.

    """

    user_id: int
    message: str


@dataclass
class AdminNotifyEvent(BaseEvent):
    """Событие уведомления администратора.

    Используется для информирования администраторов о действиях системы
    (например, удалении конфигураций или нарушениях лимитов).

    Attributes
        type: Тип события (ADMIN_NOTIFY).
        user_id: ID пользователя, к которому относится событие.
        message: Текст уведомления.

    """

    message: str
    user_id: int


@dataclass
class DeleteProxyEvent(BaseEvent):
    """Событие удаления прокси пользователя.

    Генерируется при необходимости удалить прокси-доступ пользователя,
    например после истечения подписки.

    Attributes
        type: Тип события (DELETE_PROXY).
        user_id: Telegram ID пользователя.

    """

    user_id: int


@dataclass
class DeleteVPNConfigsEvent(BaseEvent):
    """Событие удаления VPN-конфигураций пользователя.

    Используется для удаления конфигурационных файлов пользователя
    (например, при превышении лимита или окончании подписки).

    Attributes
        type: Тип события (DELETE_VPN_CONFIGS).
        user_id: Telegram ID пользователя.
        configs: Список имён файлов конфигураций для удаления.

    """

    user_id: int
    configs: list[str]


@dataclass
class DeletedVPNConfig:
    """Удалённая VPN-конфигурация (value object).

    Используется как результат удаления конфигураций из системы.

    Attributes
        file_name: Имя файла конфигурации.
        pub_key: Публичный ключ конфигурации.

    """

    file_name: str
    pub_key: str


SubscriptionEvent = (
    UserNotifyEvent | AdminNotifyEvent | DeleteProxyEvent | DeleteVPNConfigsEvent
)
