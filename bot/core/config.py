import json
from collections.abc import Iterable
from functools import cached_property
from pathlib import Path
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from box import Box
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["logger", "settings_bot", "settings_db", "bot", "dp"]

from shared.config.app_config import SettingsApp
from shared.config.db_config import SettingsDB
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SInbound(BaseModel):
    """Схема для inbounds."""

    port: int
    name: str


class SettingsBot(SettingsApp):
    """Конфигурация бота и логирования.

    Attributes
        bot_token (SecretStr):
            Токен Telegram Bot API.

        admin_ids (set[int] | str):
            Список Telegram ID администраторов (может приходить строкой или коллекцией).

        base_site (str):
            Базовый URL сайта, используемый для формирования webhook URL.

        vpn_host (str):
            Основной VPN-хост.

        vpn_test_host (str):
            Тестовый VPN-хост.

        vpn_username (str):
            Пользователь для VPN подключения.

        vpn_test_username (str):
            Пользователь для тестового VPN.

        vpn_container (str):
            Имя Docker-контейнера VPN (если используется).

        vpn_proxy (str):
            Docker-контейнер или адрес прокси VPN.

        proxy_prefix (str):
            Префикс для основного proxy (доступ через альтернативный IP).

        proxy_test_prefix (str):
            Префикс для тестового proxy.

        proxy_port (str):
            Порт прокси-сервера (по умолчанию "443").

        x_ray_host (str):
            Домен или хост XRay сервера.

        x_ray_panel_prefix (str):
            Префикс панели XRay (например subdomain для панели).

        x_ray_subscription_prefix (str):
            Префикс для subscription endpoint.

        x_ray_panel_port (int):
            Порт панели управления XRay.

        x_ray_subscription_port (int):
            Порт для подписок XRay.

        x_ray_username (SecretStr):
            Логин администратора XRay панели.

        x_ray_password (SecretStr):
            Пароль администратора XRay панели.

        inbounds (list[Inbound]):
            Список inbound-конфигураций XRay.

            Каждый элемент описывает отдельную точку входа (порт и отображаемое имя).
            Ожидается список объектов вида:

                [{"port": 443, "name": "🇧🇬 | XHTTP"},
                 {"port": 8443, "name": "🇧🇬 | TCP Reality"}]

            Может передаваться как Python-структура или JSON-строка
            (например, через переменные окружения)

        max_configs_per_user (int):
            Максимальное количество конфигов на одного пользователя.

        use_polling (bool):
            Использовать polling вместо webhook (для локальной разработки).

        use_local (bool):
            Флаг локального окружения (локальная машина или прод).

        price_map (dict[int, int]):
            Карта стоимости подписок (ключ — месяцы, значение — цена).
        price_map_premium (dict[int, int]):
                    Карта стоимости подписок премиум (ключ — месяцы, значение — цена).
        price_map_founder (dict[int, int]):
                    Карта стоимости подписок founder (ключ — месяцы, значение — цена).

        common_timeout (int):
            Базовый timeout для сетевых операций.

    Properties
        webhook_url (str):
            Сформированный URL webhook на основе base_site.

        x_ray_base_url_panel (str):
            Полный домен панели XRay (panel.{x_ray_host}).

    Methods
        parse_admin_ids(v):
            Валидирует и преобразует admin_ids в set[int].
        parse_inbounds(v):
            Преобразует входное значение в список объектов Inbound.
            Поддерживает JSON-строку и список словарей.

        messages (cached_property):
            Возвращает словарь текстов диалогов (dialogs) из bot.dialogs.dialogs_text.

    """

    # == CORE ==
    bot_token: SecretStr
    admin_ids: set[int] | str = ""
    base_site: str

    use_polling: bool = False
    use_local: bool = True

    price_map: dict[int, int] = Field(
        default_factory=lambda: {1: 100, 3: 280, 6: 520, 12: 1000, 7: 0},
        description="Карта цен подписок по месяцам",
    )
    price_map_premium: dict[int, int] = Field(
        default_factory=lambda: {1: 249, 3: 699, 6: 1290, 12: 2490, 7: 0},
        description="Карта цен подписок по месяцам",
    )
    price_map_founder: dict[int, int] = Field(
        default_factory=lambda: {1: 249, 3: 699, 6: 1290, 12: 2490, 7: 0},
        description="Карта цен подписок по месяцам",
    )
    common_timeout: int = 10

    # == VPN1 ==
    vpn_host: str
    vpn_username: str
    vpn_container: str

    # == PROXY1 ==
    proxy_prefix: str
    vpn_proxy: str
    proxy_port: str = "443"

    # == PROXY2 ==
    vpn_test_host: str = "undefined"
    vpn_test_username: str = "undefined"
    proxy_test_prefix: str = "undefined"

    # ==X-RAY ==
    x_ray_host: str = "undefined"
    x_ray_panel_prefix: str = "undefined"
    x_ray_subscription_prefix: str = "undefined"
    x_ray_panel_port: int = 0
    x_ray_subscription_port: int = 0
    x_ray_username: SecretStr
    x_ray_password: SecretStr
    inbounds: list[SInbound] = Field(default_factory=list)

    @computed_field
    def webhook_url(self) -> str:
        """Возвращает URL вебхука."""
        return f"{self.base_site}/webhook"

    @computed_field
    def x_ray_base_url_panel(self) -> str:
        """Возвращает url панели 3xui."""
        return f"panel.{self.x_ray_host}"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> set[int]:
        """Преобразует admin_ids в множество int.

        Accepts:
            - строку формата "1,2,3"
            - iterable (list, set, tuple)

        Raises
            ValueError: если значения не являются числами
            TypeError: если формат входных данных некорректен

        """
        if isinstance(v, str):
            return set(int(i) for i in v.split(",") if i.strip().isdigit())
        if isinstance(v, Iterable):
            try:
                return {int(i) for i in v}
            except (ValueError, TypeError):
                raise ValueError("admin_ids должна содержать только целые числа")

        raise TypeError("admin_ids должно быть строкой или коллекцией")

    @cached_property
    def messages(self) -> Box:
        """Кэшируемые тексты диалогов бота."""
        from bot.dialogs.dialogs_text import dialogs

        return dialogs

    @field_validator("inbounds", mode="before")
    @classmethod
    def parse_inbounds(cls, v: Any) -> list[SInbound]:
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError("INBOUNDS должен быть валидным JSON") from e
            return [SInbound(**item) for item in data]

        return v


class SettingsBucket(BaseSettings):
    """Настройки подключения к S3-совместимому хранилищу (например, Яндекс Object Storage).

    Attributes
        bucket_name (str): Имя бакета в S3, из которого будут читаться файлы.
        prefix (str): Префикс (путь внутри бакета), например 'media/amnezia_pc/'.
        endpoint_url (str): URL S3-совместимого сервиса, например 'https://storage.yandexcloud.net'.
        access_key (SecretStr): Секретный ключ доступа к сервису S3 (Access Key).
        secret_key (SecretStr): Секретный ключ доступа к сервису S3 (Secret Key).

    """

    bucket_name: str
    prefix: str
    endpoint_url: str
    access_key: SecretStr
    secret_key: SecretStr

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),
            str(BASE_DIR / ".env.local"),
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings_bot = SettingsBot()  # type: ignore
settings_db = SettingsDB()  # type: ignore
settings_bucket = SettingsBucket()  # type: ignore
# settings_ai = SettingsAI()

LoggerConfig(
    log_dir=BASE_DIR / "bot" / "logs",
    logger_level_stdout=settings_bot.logger_level_stdout,
    logger_level_file=settings_bot.logger_level_file,
    logger_error_file=settings_bot.logger_error_file,
)
# Инициализируем бота и диспетчер
bot: Bot = Bot(
    token=settings_bot.bot_token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
# Хранилище FSM
storage = RedisStorage.from_url(
    str(settings_db.redis_url),
    state_ttl=3600,  # ⏰ время жизни состояния (в секундах)
    data_ttl=3600,  # ⏰ время жизни данных FSM
)
# Это если работать без Redis
# dp = Dispatcher(storage=MemoryStorage())
# Это если работать через Redis
dp = Dispatcher(storage=storage)

if __name__ == "__main__":
    print(settings_bot.price_map)
    print(settings_bot.price_map[1])
