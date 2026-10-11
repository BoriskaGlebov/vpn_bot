from urllib.parse import quote_plus

from pydantic import SecretStr
from pydantic_settings import SettingsConfigDict
from sqlalchemy import URL

from shared.config.app_config import SettingsCommon


class PostgresSettings(SettingsCommon):
    """Конфигурация базы данных POSTGRES.

    Attributes
        host (str): Хост PostgreSQL-сервера. По умолчанию "localhost".
        port (int): Порт PostgreSQL-сервера. По умолчанию 5432.
        user (str): Имя пользователя для подключения к базе данных.
        password (SecretStr): Пароль пользователя для подключения к базе данных.
        database (str): Имя базы данных.
        embedding_dim (int): Размерность Эмбеддингов, которые можно записать в БД. В яндекс по умолчанию 256.

    Properties
        url (URL): Строка подключения к PostgreSQL в формате
            `postgresql+asyncpg://user:password@host:port/database`,
            собранная через `sqlalchemy.URL.create`. Формируется автоматически
            из указанных выше атрибутов. Обычный `@property`, а не
            `computed_field` — иначе пароль попадал бы в `model_dump()`
            открытым текстом в обход маскировки `SecretStr`.

    """

    host: str = "postgres"
    port: int = 5432
    user: str
    password: SecretStr
    database: str
    embedding_dim: int = 256

    @property
    def url(self) -> URL:
        """Строка подключения к PostgreSQL через asyncpg.

        Returns
           URL: Объект `sqlalchemy.URL` (принимается `create_async_engine`
               напрямую). Экранирование `user`/`password` (спецсимволы вроде
               `@`, `:`, `/`) выполняет сам `URL.create`, вручную `quote_plus`
               звать не нужно — в отличие от Redis ниже, где драйвер ждёт
               готовую строку.

        """
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.user,
            password=self.password.get_secret_value(),
            host=self.host,
            port=self.port,
            database=self.database,
        )

    model_config = SettingsConfigDict(env_prefix="DB_")


class RedisSettings(SettingsCommon):
    """Конфигурация базы данных REDIS.

    Attributes
        password (SecretStr): Пароль для подключения к Redis.
        host (str): Хост Redis-сервера. По умолчанию "redis".
        port (int): Порт Redis-сервера. По умолчанию 6379.
        db (int): Номер базы данных Redis. По умолчанию 0.
        user (str) : Имя пользователя Redis для приложения.
        default_expire (int) : Время жизни ключей в Redis по умолчанию (в секундах). По умолчанию 43200 секунд (12 часов).

    Properties
        url (str): Строка подключения к Redis в формате
        `redis://:password@host:port/db_number`. Обычный `@property`, а не
        `computed_field` — иначе пароль попадал бы в `model_dump()` открытым
        текстом в обход маскировки `SecretStr`.

    """

    host: str = "redis"
    port: int = 6379
    password: SecretStr
    user: str
    db: int = 0
    default_expire: int = 43200

    @property
    def url(self) -> str:
        """Строка подключения к Redis.

        Returns
           str: URL подключения к базе данных. `user`/`password` экранированы
               через `quote_plus`, так что спецсимволы (`@`, `:`, `/` и т.п.)
               не разрывают URL.

        """
        user = quote_plus(self.user)
        password = quote_plus(self.password.get_secret_value())
        return f"redis://{user}:{password}@{self.host}:{self.port}/{self.db}"

    model_config = SettingsConfigDict(env_prefix="REDIS_")
