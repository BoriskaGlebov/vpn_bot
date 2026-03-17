from pydantic import SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.config.app_config import BASE_DIR


class SettingsDB(BaseSettings):
    """Конфигурация базы данных и Redis для проекта.

    Attributes
        db_host (str): Хост PostgreSQL-сервера. По умолчанию "localhost".
        db_port (int): Порт PostgreSQL-сервера. По умолчанию 5432.
        db_user (str): Имя пользователя для подключения к базе данных.
        db_password (SecretStr): Пароль пользователя для подключения к базе данных.
        db_database (str): Имя базы данных.
        redis_password (SecretStr): Пароль для подключения к Redis.
        redis_host (str): Хост Redis-сервера. По умолчанию "localhost".
        redis_port (int): Порт Redis-сервера. По умолчанию 6379.
        num_db (int): Номер базы данных Redis. По умолчанию 0.
        redis_user (str) : Имя пользователя Redis для приложения.
        default_expire (int) : Время жизни ключей в Redis по умолчанию (в секундах). По умолчанию 3600 секунд (1 час).
        embedding_dim (int): Размерность Эмбеддингов, которые можно записать в БД. В яндекс по умолчанию 256.
    Properties
        database_url (str): Строка подключения к PostgreSQL в формате
            `postgresql+asyncpg://user:password@host:port/database`.
            Формируется автоматически из указанных выше атрибутов.
        redis_url (str): Строка подключения к Redis в формате
            `redis://:password@host:port/db_number`.
    Configuration
        model_config (SettingsConfigDict): Конфигурация pydantic settings
            (путь до .env, кодировка и поведение при лишних переменных).

    """

    db_host: str = "postgres"
    db_port: int = 5432
    db_user: str
    db_password: SecretStr
    db_database: str

    redis_password: SecretStr
    redis_host: str = "redis"
    redis_port: int = 6379
    default_expire: int = 3600
    redis_user: str
    num_db: int = 0
    embedding_dim: int = 256

    model_config = SettingsConfigDict(
        env_file=[
            str(BASE_DIR / ".env"),  # базовые значения
            str(BASE_DIR / ".env.local"),  # локальные переопределяют .env
        ],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    def database_url(self) -> str:
        """Строка подключения к PostgreSQL через asyncpg.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password.get_secret_value()}@"
            f"{self.db_host}:{self.db_port}/{self.db_database}"
        )

    @computed_field
    def redis_url(self) -> str:
        """Строка подключения к Redis.

        Returns
           str: URL подключения к базе данных.

        """
        return (
            f"redis://{self.redis_user}:{self.redis_password.get_secret_value()}@"
            f"{self.redis_host}:{self.redis_port}/{self.num_db}"
        )
