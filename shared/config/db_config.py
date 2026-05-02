from pydantic import SecretStr, computed_field
from pydantic_settings import SettingsConfigDict

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
        url (str): Строка подключения к PostgreSQL в формате
            `postgresql+asyncpg://user:password@host:port/database`.
            Формируется автоматически из указанных выше атрибутов.

    """

    host: str = "postgres"
    port: int = 5432
    user: str
    password: SecretStr
    database: str
    embedding_dim: int = 256

    @computed_field
    def url(self) -> str:
        """Строка подключения к PostgreSQL через asyncpg.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    model_config = SettingsConfigDict(env_prefix="DB_")


class RedisSettings(SettingsCommon):
    """Конфигурация базы данных REDIS.

    Attributes
        redis_password (SecretStr): Пароль для подключения к Redis.
        redis_host (str): Хост Redis-сервера. По умолчанию "redis".
        redis_port (int): Порт Redis-сервера. По умолчанию 6379.
        num_db (int): Номер базы данных Redis. По умолчанию 0.
        redis_user (str) : Имя пользователя Redis для приложения.
        default_expire (int) : Время жизни ключей в Redis по умолчанию (в секундах). По умолчанию 3600 секунд (1 час).

    Properties
        url (str): Строка подключения к Redis в формате
        `redis://:password@host:port/db_number`.

    """

    host: str = "redis"
    port: int = 6379
    password: SecretStr
    user: str
    db: int = 0
    default_expire: int = 3600

    @computed_field
    def url(self) -> str:
        """Строка подключения к Redis.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"redis://{self.user}:{self.password.get_secret_value()}@"
            f"{self.host}:{self.port}/{self.db}"
        )

    model_config = SettingsConfigDict(env_prefix="REDIS_")
