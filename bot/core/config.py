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
from pydantic_settings import SettingsConfigDict

from shared.config.db_config import RedisSettings

__all__ = ["logger", "settings_bot", "bot", "dp"]

from shared.config.app_config import SettingsApp, SettingsCommon
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SInbound(BaseModel):
    """Схема для inbounds."""

    port: int
    name: str


class BotSettings(SettingsCommon):
    token: SecretStr
    admin_ids: set[int] | str = ""
    base_site: str
    use_polling: bool = False

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

    @computed_field
    def webhook_url(self) -> str:
        """Возвращает URL вебхука."""
        return f"{self.base_site}/webhook"

    model_config = SettingsConfigDict(env_prefix="BOT_")


class ApiSettings(SettingsCommon):
    url: str = "api"
    port: int = 8089

    model_config = SettingsConfigDict(env_prefix="API_")


class VPNSettingsMain(SettingsCommon):
    host: str
    username: str
    container: str = "amnezia-awg2"
    container_old: str = "amnezia-awg"
    use_local: bool = True

    model_config = SettingsConfigDict(env_prefix="MAIN_VPN_")


class ProxySettingsMain(SettingsCommon):
    prefix: str
    container: str = "telemt"
    port: str = "443"
    model_config = SettingsConfigDict(env_prefix="MAIN_PROXY_")


class VPNSettingsFI(SettingsCommon):
    host: str | None = None
    username: str | None = None
    container: str = "amnezia-awg2"
    use_local: bool = False

    model_config = SettingsConfigDict(env_prefix="FI_VPN_")


class ProxySettingsFI(SettingsCommon):
    prefix: str | None = None
    container: str = "telemt"
    port: str = "443"
    model_config = SettingsConfigDict(env_prefix="FI_PROXY_")


class XRaySettingsSOF(SettingsCommon):
    host: str = "undefined"
    panel_prefix: str = "undefined"
    subscription_prefix: str = "undefined"

    panel_port: int = 0
    subscription_port: int = 0

    username: SecretStr
    password: SecretStr

    inbounds: list[SInbound] = Field(default_factory=list)

    @computed_field
    def url_panel(self) -> str:
        """Возвращает url панели 3xui."""
        return f"panel.{self.host}"

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

    model_config = SettingsConfigDict(env_prefix="SOF_X_RAY_")


class PricingSettings(SettingsCommon):
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


class BucketSettings(SettingsCommon):
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


class Settings(SettingsCommon):
    """Конфигурация бота и логирования.

    Attributes
        bot_token (SecretStr):
            Токен Telegram Bot API.

        admin_ids (set[int] | str):
            Список Telegram ID администраторов (может приходить строкой или коллекцией).

        base_site (str):
            Базовый URL сайта, используемый для формирования webhook URL.

        api_url (str): Адрес api интеграции.
        api_port (int): Порт для api.

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

    core: SettingsApp = Field(default_factory=SettingsApp)

    bot: BotSettings = Field(default_factory=BotSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    vpn_main: VPNSettingsMain = Field(default_factory=VPNSettingsMain)
    proxy_main: ProxySettingsMain = Field(default_factory=ProxySettingsMain)

    vpn_fi: VPNSettingsFI = Field(default_factory=VPNSettingsFI)
    proxy_fi: ProxySettingsFI = Field(default_factory=ProxySettingsFI)

    xray_sof: XRaySettingsSOF = Field(default_factory=XRaySettingsSOF)

    pricing: PricingSettings = Field(default_factory=PricingSettings)

    bucket: BucketSettings = Field(default_factory=BucketSettings)

    redis: RedisSettings = Field(default_factory=RedisSettings)

    @cached_property
    def messages(self) -> Box:
        """Кэшируемые тексты диалогов бота."""
        from bot.dialogs.dialogs_text import dialogs

        return dialogs


settings_bot = Settings()  # type: ignore

# settings_ai = SettingsAI()

LoggerConfig(
    log_dir=BASE_DIR / "bot" / "logs",
    logger_level_stdout=settings_bot.core.logger_level_stdout,
    logger_level_file=settings_bot.core.logger_level_file,
    logger_error_file=settings_bot.core.logger_error_file,
)
# Инициализируем бота и диспетчер
bot: Bot = Bot(
    token=settings_bot.bot.token.get_secret_value(),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
# Хранилище FSM
storage = RedisStorage.from_url(
    str(settings_bot.redis.url),
    state_ttl=settings_bot.redis.default_expire,  # ⏰ время жизни состояния (в секундах)
    data_ttl=settings_bot.redis.default_expire,  # ⏰ время жизни данных FSM
)
# Это если работать без Redis
# dp = Dispatcher(storage=MemoryStorage())
# Это если работать через Redis
dp = Dispatcher(storage=storage)

if __name__ == "__main__":
    print(settings_bot)
    print("*" * 15)
    print(settings_bot.redis)
    print("*" * 15)
