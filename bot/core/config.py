import json
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

from bot.app_error.base_error import (
    ProxyNotConfiguredError,
    VPNNodeNotFoundError,
    XRayNotConfiguredError,
)
from shared.config.app_config import SettingsApp, SettingsCommon, load_toml_config
from shared.config.db_config import RedisSettings
from shared.config.logger_config import LoggerConfig

__all__ = ["logger", "settings_bot", "bot", "dp"]

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SInbound(BaseModel):
    """Модель inbound-конфигурации XRay.

    Attributes
        port (int): Порт, на котором слушает inbound.
        name (str): Человекочитаемое имя inbound (например, с флагом страны).

    """

    port: int
    name: str


class BotSettings(SettingsCommon):
    """Настройки Telegram-бота.

    Attributes
        token (SecretStr): Токен Telegram Bot API.
        admin_ids (set[int] | str): Список ID администраторов.
            Может передаваться как:
            - строка: "1,2,3"
            - коллекция: list[int] | set[int] | tuple[int, ...]
        base_site (str): Базовый URL сайта (используется для webhook).
        use_polling (bool): Использовать polling вместо webhook.

    Properties
        webhook_url (str): Полный URL webhook.

    """

    token: SecretStr
    base_site: str
    use_polling: bool = False

    @computed_field
    def webhook_url(self) -> str:
        """Формирует URL webhook.

        Returns
            str: URL вида "{base_site}/webhook".

        """
        return f"{self.base_site}/webhook"

    model_config = SettingsConfigDict(env_prefix="BOT_")


class SchedulerSettings(SettingsCommon):
    """Настройки расписания плановой проверки подписок.

    Позволяет переключать проверку между быстрым интервалом (для локальной
    отладки) и боевым cron-расписанием без ручной правки кода — выбор
    зависит только от того, что задано в `app_config.{toml,develop.toml}`
    для текущей `STAGE`.

    Attributes
        interval_seconds (int | None): Если задано — джоба запускается через
            фиксированный интервал в секундах (используется в dev/local).
            Если не задано (None) — используется cron-расписание
            (`cron_hour`:`cron_minute`), как в проде.
        cron_hour (int): Час запуска по cron-расписанию.
        cron_minute (int): Минута запуска по cron-расписанию.

    """

    interval_seconds: int | None = None
    cron_hour: int = 8
    cron_minute: int = 0

    model_config = SettingsConfigDict(env_prefix="SCHEDULER_")


class ApiSettings(SettingsCommon):
    """Настройки API-сервиса.

    Attributes
        url (str): Хост или путь API.
        port (int): Порт API.
        secret (SecretStr): Общий секрет для подписи запросов бота к api/
            (заголовок X-Internal-Secret). Должен совпадать со значением
            INTERNAL_API_SECRET на стороне api/.

    """

    url: str = "api"
    port: int = 8089
    secret: SecretStr = Field(
        default=SecretStr("secret"),
        validation_alias="INTERNAL_API_SECRET",
    )

    model_config = SettingsConfigDict(env_prefix="API_")


class ProxySettings(SettingsCommon):
    """Настройки прокси-контейнера.

    Attributes
        prefix (str): Префикс домена/URL.
        container (str): Имя Docker-контейнера.
        port (int): Порт прокси.

    """

    prefix: str
    container: str = "telemt"
    port: int = 443


class XRaySettings(SettingsCommon):
    """Настройки XRay (3x-ui панель и подписки).

    Attributes
        host (str): Домен XRay.
        panel_prefix (str): Префикс панели управления.
        subscription_prefix (str): Префикс подписок.
        panel_port (int): Порт панели.
        subscription_port (int): Порт подписок.
        username (SecretStr): Логин панели.
        password (SecretStr): Пароль панели.
        inbounds (list[SInbound]): Список inbound-конфигураций.

    Properties
        url_panel (str): Домен панели (panel.{host}).

    """

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
        """Возвращает домен панели XRay.

        Returns
            str: Домен вида "panel.{host}".

        """
        return f"panel.{self.host}"

    @field_validator("inbounds", mode="before")
    @classmethod
    def parse_inbounds(cls, v: Any) -> list[SInbound]:
        """Парсит inbound-конфигурации.

        Args:
            v (Any): JSON-строка или список словарей.

        Returns
            list[SInbound]: Список inbound-объектов.

        Raises
            ValueError: Если JSON некорректен.

        """
        if isinstance(v, str):
            try:
                data = json.loads(v)
            except json.JSONDecodeError as e:
                raise ValueError("INBOUNDS должен быть валидным JSON") from e
            return [SInbound(**item) for item in data]

        return v

    model_config = SettingsConfigDict(env_prefix="SOF_X_RAY_")


class VPNNode(SettingsCommon):
    """Конфигурация VPN-ноды.

    Attributes
        host (str): Хост ноды.
        username (str): Пользователь для подключения.
        container (str): Имя Docker-контейнера.
        container_old (str | None): Старое имя контейнера.
        use_local (bool): Использовать локальную ноду.
        location_prefix (str): Префикс для определения локации файла, базово Франция
        flag (str): Флаг страны для кнопок.
        proxy (ProxySettings | None): Настройки прокси.
        xray (XRaySettingsSOF | None): Настройки XRay.

    """

    host: str
    username: str
    container: str
    container_old: str | None = None
    use_local: bool = False
    location_prefix: str = "FR"
    flag: str = "🏴‍☠️"
    proxy: ProxySettings | None = None
    xray: XRaySettings | None = None

    def require_xray(self) -> XRaySettings:
        """Гарантирует наличие XRay-конфигурации.

        Returns
            XRaySettings: Настройки XRay.

        Raises
            XRayNotConfiguredError: Если XRay не настроен.

        """
        if self.xray is None:
            raise XRayNotConfiguredError(self.host)
        return self.xray

    def require_proxy(self) -> ProxySettings:
        """Гарантирует наличие Proxy-конфигурации.

        Returns
            ProxySettings: Настройки Proxy.

        Raises
            ProxyNotConfiguredError: Если Proxy не настроен.

        """
        if self.proxy is None:
            raise ProxyNotConfiguredError(self.host)
        return self.proxy


class VPNRegistry(SettingsCommon):
    """Реестр VPN-нод.

    Attributes
        nodes (dict[str, VPNNode]): Словарь нод по имени.

    """

    nodes: dict[str, VPNNode]

    def get(self, name: str) -> VPNNode:
        """Возвращает ноду по имени.

        Args:
            name (str): Имя ноды.

        Returns
            VPNNode: Найденная нода.

        Raises
            VPNNodeNotFoundError: Если нода не найдена.

        """
        try:
            return self.nodes[name]
        except KeyError as exc:
            raise VPNNodeNotFoundError(name) from exc

    def get_optional(self, name: str) -> VPNNode | None:
        """Возвращает ноду по имени или None, если она не сконфигурирована.

        В отличие от `get`, не бросает исключение. Используется для нод,
        которые допустимо временно не поднимать (например, ещё не
        развёрнутая при масштабировании локация) — вызывающий код сам
        решает, как деградировать при отсутствии ноды.

        Args:
            name (str): Имя ноды.

        Returns
            VPNNode | None: Найденная нода либо None.

        """
        return self.nodes.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.nodes

    @property
    def main(self) -> VPNNode:
        """Основная нода."""
        return self.get("main")

    @property
    def sof(self) -> VPNNode:
        """Нода SOF."""
        return self.get("sof")

    @property
    def fi(self) -> VPNNode | None:
        """Нода FI.

        В отличие от `main`/`sof` может быть не сконфигурирована —
        вызывающий код обязан проверять на None перед использованием.
        """
        return self.get_optional("fi")

    @property
    def waw(self) -> VPNNode | None:
        """Нода WAW."""
        return self.get_optional("waw")


class VPNSettingsMain(SettingsCommon):
    host: str
    username: str
    container: str = "amnezia-awg2"
    container_old: str = "amnezia-awg"
    use_local: bool = True

    model_config = SettingsConfigDict(env_prefix="MAIN_VPN_")


class PricingSettings(SettingsCommon):
    """Настройки тарифов.

    Attributes
        price_map (dict[int, int]): Базовые тарифы (месяцы → цена).
        price_map_premium (dict[int, int]): Премиум тарифы.
        price_map_founder (dict[int, int]): Founder тарифы.

    """

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
        backup_encryption_key (SecretStr | None): Fernet-ключ для шифрования бэкапов
            конфигураций VPN-контейнеров перед загрузкой в S3 (в них приватные ключи
            WireGuard). Генерируется один раз: `Fernet.generate_key()`.

    """

    bucket_name: str
    prefix: str
    endpoint_url: str
    access_key: SecretStr
    secret_key: SecretStr
    backup_encryption_key: SecretStr | None = None


class PaymentSettings(SettingsCommon):
    """Настройки интеграции с платёжным шлюзом.

    Attributes
        merchant_id (SecretStr): Идентификатор мерчанта,
            предоставленный платёжной системой.
        api_key (SecretStr): Секретный API-ключ для
            аутентификации запросов к платёжному API.

    """

    merchant_id: SecretStr
    api_key: SecretStr


class Settings(SettingsCommon):
    """Агрегированная конфигурация приложения.

    Объединяет все настройки бота, API, VPN, хранилищ и инфраструктуры
    в единую типизированную структуру.

    Attributes
        core (SettingsApp): Базовые настройки приложения
            (логирование, таймауты и пр.).

        bot (BotSettings): Настройки Telegram-бота
            (токен, администраторы, webhook/polling).

        scheduler (SchedulerSettings): Расписание плановой проверки подписок
            (интервал для dev или cron-время для прода).

        api (ApiSettings): Конфигурация API-сервиса
            (хост, порт).

        vpn (VPNRegistry): Реестр VPN-нод.
            Содержит именованные конфигурации серверов (main, sof, fi и др.).

        pricing (PricingSettings): Настройки тарифов и цен.

        bucket (BucketSettings): Настройки S3-совместимого хранилища
            (например, Yandex Object Storage).

        redis (RedisSettings): Настройки Redis
            (подключение и TTL для FSM/кэша).

        payment (PaymentSettings): Настройки интеграции с сервисом оплаты

    Properties
        messages (Box): Тексты диалогов бота.
            Загружаются из `bot.dialogs.dialogs_text` и кэшируются
            после первого обращения.

    Notes
        - Конфигурация загружается из TOML + переменных окружения.
        - Все вложенные модели валидируются через Pydantic.
        - Используется строгая типизация для совместимости с mypy.

    """

    core: SettingsApp = Field(default_factory=SettingsApp)

    bot: BotSettings = Field(default_factory=BotSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    vpn: VPNRegistry = Field(default_factory=VPNRegistry)

    pricing: PricingSettings = Field(default_factory=PricingSettings)

    bucket: BucketSettings = Field(default_factory=BucketSettings)

    redis: RedisSettings = Field(default_factory=RedisSettings)

    payment: PaymentSettings = Field(default_factory=PaymentSettings)

    @cached_property
    def messages(self) -> Box:
        """Возвращает тексты диалогов бота.

        Кэшируется после первого вызова.

        Returns
            Box: Объект с текстами диалогов.

        """
        from bot.dialogs.dialogs_text import dialogs

        return dialogs


toml_loader = load_toml_config()
settings_bot = Settings(**toml_loader)  # type: ignore

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
# # Хранилище FSM
storage = RedisStorage.from_url(
    str(settings_bot.redis.url),
    state_ttl=settings_bot.redis.default_expire,  # ⏰ время жизни состояния (в секундах)
    data_ttl=settings_bot.redis.default_expire,  # ⏰ время жизни данных FSM
)
# Это если работать без Redis
# dp = Dispatcher(storage=MemoryStorage())
# Это если работать через Redis
dp = Dispatcher(storage=storage)
