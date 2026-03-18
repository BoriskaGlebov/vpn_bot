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
from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["logger", "settings_bot", "settings_db", "bot", "dp"]

from shared.config.app_config import SettingsApp
from shared.config.db_config import SettingsDB
from shared.config.logger_config import LoggerConfig

BASE_DIR = Path(__file__).resolve().parent.parent
# TODO убрать в дальнейшем закомментированный код


class SettingsBot(SettingsApp):
    """Конфигурация бота и логирования.

    Attributes
        bot_token (SecretStr): Токен бота для подключения к Telegram Bot API.
        admin_ids (Union[Set[int], str]): Список Telegram ID администраторов с расширенными правами.
        base_site (str): Базовый URL сайта, используемый для формирования вебхука.
        vpn_host (str): Хост VPN-сервера.
        vpn_username (str): Имя пользователя для подключения к VPN.
        vpn_container (str): Имя Docker-контейнера VPN (если используется).
        vpn_proxy (str) : Имя Docker-контейнера PROXY (если используется).
        proxy_port (str) : Порт для прокси на сервере.
        max_configs_per_user (int): Максимальное количество файлов конфига для одного пользователя
        use_polling (bool): Использовать polling вместо webhook (по умолчанию False, удобно для тестов).
        use_local (bool): Учитывать место развертывание бота, локальная машина или целевой хост.
        messages (dict[str, Any]): Словарь с текстами сообщений бота (диалоги, подсказки и т.д.).
        price_map (dict[int, int]): Карта цен подписок по месяцам, может быть задана через .env в JSON.
    Properties
        webhook_url (str): URL вебхука. Формируется автоматически на основе BASE_SITE.

    """

    bot_token: SecretStr
    admin_ids: set[int] | str = ""
    base_site: str

    vpn_host: str
    vpn_username: str
    vpn_container: str
    vpn_proxy: str
    proxy_port: str = "8443"
    max_configs_per_user: int = 10

    use_polling: bool = False
    use_local: bool = True

    price_map: dict[int, int] = Field(
        default_factory=lambda: {1: 100, 3: 280, 6: 520, 12: 1000, 7: 0},
        description="Карта цен подписок по месяцам",
    )

    @computed_field
    def webhook_url(self) -> str:
        """Возвращает URL вебхука."""
        return f"{self.base_site}/webhook"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: Any) -> set[int]:
        """Парсит строку с ID администраторов в множество целых чисел."""
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
        from bot.dialogs.dialogs_text import dialogs

        return dialogs


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
    log_dir=Path(__file__).resolve().parent / "logs",
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
