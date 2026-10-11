from shared.config.db_config import PostgresSettings, RedisSettings

SPECIAL_PASSWORD = "p@ss:w/ord#1"


def test_postgres_url_escapes_special_characters() -> None:
    settings = PostgresSettings(
        user="u@ser",
        password=SPECIAL_PASSWORD,
        database="db",
        host="h",
        port=5432,
    )

    url = settings.url

    assert url == "postgresql+asyncpg://u%40ser:p%40ss%3Aw%2Ford%231@h:5432/db"


def test_postgres_model_dump_does_not_leak_password() -> None:
    settings = PostgresSettings(
        user="u",
        password=SPECIAL_PASSWORD,
        database="db",
    )

    dumped = settings.model_dump()

    assert "url" not in dumped
    assert SPECIAL_PASSWORD not in str(dumped)


def test_redis_url_escapes_special_characters() -> None:
    settings = RedisSettings(
        user="u@ser",
        password=SPECIAL_PASSWORD,
        host="h",
        port=6379,
        db=0,
    )

    url = settings.url

    assert url == "redis://u%40ser:p%40ss%3Aw%2Ford%231@h:6379/0"


def test_redis_model_dump_does_not_leak_password() -> None:
    settings = RedisSettings(user="u", password=SPECIAL_PASSWORD)

    dumped = settings.model_dump()

    assert "url" not in dumped
    assert SPECIAL_PASSWORD not in str(dumped)
