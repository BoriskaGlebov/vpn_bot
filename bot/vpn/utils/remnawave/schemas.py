from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class RemnawaveBaseModel(BaseModel):
    """Базовая модель для обмена данными с панелью Remnawave.

    Панель принимает и возвращает поля в camelCase, тогда как в коде
    бота принято snake_case — `alias_generator` транслирует одно в
    другое автоматически. `populate_by_name` позволяет собирать модель
    и по snake_case-имени поля, и по camelCase-алиасу, а `extra="ignore"`
    не даёт упасть на незнакомых полях, которые панель добавит в будущем.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class RemnawaveUserCreate(RemnawaveBaseModel):
    """Тело запроса `POST /api/users` — создание пользователя на панели.

    Attributes
        username (str): Имя пользователя на панели.
        telegram_id (int): Telegram ID владельца.
        expire_at (datetime): Момент окончания действия доступа.
        hwid_device_limit (int): Лимит устройств (HWID).
        active_internal_squads (list[UUID]): Squad'ы, к которым подключается
            пользователь.
        status (str): Статус пользователя на панели.

    """

    username: str
    telegram_id: int
    expire_at: datetime
    hwid_device_limit: int
    active_internal_squads: list[UUID]
    status: str = "active"


class RemnawaveUserUpdate(RemnawaveBaseModel):
    """Тело запроса `PATCH /api/users` — изменение пользователя на панели.

    Attributes
        uuid (UUID): Идентификатор пользователя на панели.
        expire_at (datetime | None): Новый момент окончания действия доступа.
        hwid_device_limit (int | None): Новый лимит устройств (HWID).
        active_internal_squads (list[UUID] | None): Новый список squad'ов.
        status (str | None): Новый статус пользователя на панели.

    """

    uuid: UUID
    expire_at: datetime | None = None
    hwid_device_limit: int | None = None
    active_internal_squads: list[UUID] | None = None
    status: str | None = None


class RemnawaveUserResponse(RemnawaveBaseModel):
    """Ответ панели Remnawave с данными пользователя.

    Attributes
        uuid (UUID): Идентификатор пользователя на панели.
        short_uuid (str): Короткий идентификатор, используемый в ссылке
            подписки.
        username (str): Имя пользователя на панели.
        telegram_id (int): Telegram ID владельца.
        subscription_url (str): Ссылка на подписку пользователя.
        expire_at (datetime): Момент окончания действия доступа.
        hwid_device_limit (int): Лимит устройств (HWID).
        active_internal_squads (list[UUID]): Squad'ы, к которым подключён
            пользователь.
        status (str): Статус пользователя на панели.
        created_at (datetime): Момент создания пользователя.
        updated_at (datetime): Момент последнего изменения пользователя.

    """

    uuid: UUID
    short_uuid: str
    username: str
    telegram_id: int
    subscription_url: str
    expire_at: datetime
    hwid_device_limit: int
    active_internal_squads: list[UUID]
    status: str
    created_at: datetime
    updated_at: datetime
