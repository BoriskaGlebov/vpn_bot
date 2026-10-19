from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import wraps
from typing import Annotated, Any, Literal, TypeVar

from sqlalchemy import DateTime, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from api.core.config import settings_api

engine = create_async_engine(
    settings_api.db.url,
    pool_size=settings_api.db.pool_size,
    max_overflow=settings_api.db.max_overflow,
    pool_pre_ping=settings_api.db.pool_pre_ping,
    pool_recycle=settings_api.db.pool_recycle,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


IsolationLevel = Literal["READ COMMITTED", "REPEATABLE READ", "SERIALIZABLE"]


def connection(isolation_level: IsolationLevel | None = None) -> Callable[[F], F]:
    """Декоратор для автоматического управления асинхронной сессией базы данных и транзакцией.

    Этот декоратор создаёт сессию `AsyncSession`, оборачивает выполнение функции в транзакцию,
    автоматически выполняет commit или rollback при исключении и закрывает сессию после завершения.

    Args:
        isolation_level (str, optional): Уровень изоляции транзакции. Возможные значения:
            - "READ COMMITTED" — по умолчанию, для большинства CRUD-операций.
            - "REPEATABLE READ" — для сложных аналитических запросов или расчётов.
            - "SERIALIZABLE" — полная защита от конкурентных изменений (например, финансы).

    Returns
        function: Декорированная асинхронная функция, которой будет передан аргумент `session` типа `AsyncSession`.

    Examples
        @connection(isolation_level="SERIALIZABLE")
        async def create_user(username: str, session: AsyncSession):
            user = User(username=username)
            session.add(user)

    """

    def decorator(method: F) -> F:
        @wraps(method)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if isinstance(kwargs.get("session"), AsyncSession):
                return await method(*args, **kwargs)
            async with async_session() as session:
                try:
                    if isolation_level:
                        # `SET TRANSACTION ISOLATION LEVEL` сырым SQL применяется
                        # к транзакции, открытой ЭТИМ execute — а следующий
                        # `session.begin()` на сессии с уже начатой транзакцией
                        # бросает InvalidRequestError. `connection(execution_options=...)`
                        # устанавливает уровень на соединении до начала работы с
                        # ним и не требует отдельного `begin()` — транзакция
                        # начинается автоматически (SQLAlchemy autobegin) при
                        # первом запросе внутри `method`.
                        await session.connection(
                            execution_options={"isolation_level": isolation_level}
                        )
                    result = await method(*args, session=session, **kwargs)
                except SQLAlchemyError:
                    await session.rollback()
                    raise
                else:
                    await session.commit()
                    return result

        return wrapper  # type: ignore[return-value]

    return decorator


# Подстроки в именах полей, по которым значение маскируется перед логированием/
# выводом модели в строку. Общая реализация для `BaseDAO._redact` (параметры
# DAO-операций) и `Base.to_dict_redacted` (колонки модели) — чтобы маскирование
# не обходилось через `__repr__`/`to_dict`, которые читают значения напрямую
# с объекта, а не из словаря параметров DAO (см. #238).
_SENSITIVE_KEY_MARKERS = ("password", "secret", "token", "payload", "api_key", "card")


def redact(values: dict[str, Any]) -> dict[str, Any]:
    """Маскирует потенциально чувствительные поля словаря по имени ключа.

    Args:
        values: Словарь значений (параметров DAO-операции либо колонок модели).

    Returns
        dict[str, Any]: Копия словаря; значения ключей, содержащих
            чувствительные подстроки (см. `_SENSITIVE_KEY_MARKERS`), заменены
            на `"***"`.

    """
    return {
        k: (
            "***"
            if any(marker in k.lower() for marker in _SENSITIVE_KEY_MARKERS)
            else v
        )
        for k, v in values.items()
    }


int_pk = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
# timezone=True — см. #255: без неё колонка хранит TIMESTAMP WITHOUT TIME
# ZONE, и created_at/updated_at (которые ставит Postgres через func.now())
# оказываются в одной таблице с полями, которые ставит сам процесс (напр.
# PaymentTransaction.paid_at/confirmed_at) без единой договорённости о зоне.
created_at = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now())
]
updated_at = Annotated[
    datetime,
    mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    ),
]
str_uniq = Annotated[str, mapped_column(unique=True, nullable=False)]
str_null_true = Annotated[str, mapped_column(nullable=True)]


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей базы данных.

    Предоставляет общие атрибуты и методы для всех моделей,
    включая автоматическое определение имени таблицы, поля даты создания
    и обновления записи, а также метод преобразования объекта в словарь.

    Attributes
        id (Any): Первичный ключ. Объявлен здесь только для типизации (без
            `Mapped`/`mapped_column`, то есть не создаёт колонку и не участвует
            в маппинге) — каждая модель переопределяет его своим конкретным
            `Mapped[int]` (`int_pk`) или `Mapped[UUID]`. Цель — дать
            `BaseDAO[T]` типобезопасный доступ к `cls.model.id` независимо от
            конкретного типа PK, без `# type: ignore[attr-defined]` на каждом
            обращении.
        created_at (Mapped[datetime]): Дата и время создания записи.
        updated_at (Mapped[datetime]): Дата и время последнего обновления записи.

    """

    __abstract__ = True

    id: Any

    @declared_attr.directive
    def __tablename__(self) -> str:
        """Формирует имя таблицы."""
        return f"{self.__name__.lower()}s"

    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]

    def to_dict(self) -> dict[str, Any]:
        """Преобразует экземпляр модели в словарь.

        Ключи — имена колонок, значения — соответствующие данные. Значения не
        маскированы — вызывающий код сам решает, попадёт ли результат в лог
        (см. `to_dict_redacted` для безопасного по умолчанию варианта).

        Returns
            dict[str, Any]: Словарь с данными модели.

        """
        return {c.name: getattr(self, c.name) for c in self.__mapper__.columns}

    def to_dict_redacted(self) -> dict[str, Any]:
        """`to_dict()` с маскированием чувствительных полей по имени колонки.

        Для осознанного подробного вывода модели (отладка, ad-hoc логирование) —
        в отличие от `__repr__`/`__str__`, которые печатают только id и не
        предназначены для диагностики содержимого записи.

        Returns
            dict[str, Any]: Словарь с данными модели; чувствительные поля
                (см. `_SENSITIVE_KEY_MARKERS`) заменены на `"***"`.

        """
        return redact(self.to_dict())

    def __repr__(self) -> str:
        """Возвращает краткое представление модели: класс и `id`.

        Раньше печатались значения всех колонок, то есть любое попадание
        объекта модели в f-строку лога, `str()`/`repr()` в сообщении об
        ошибке SQLAlchemy или трейсбек с `diagnose=True` (см. #226) выводило
        запись целиком — маскирование `BaseDAO._redact` на это не влияет,
        потому что оно применяется к словарям параметров DAO, а не к самому
        объекту. Подробный вывод с маскированием — `to_dict_redacted()`,
        вызывается осознанно.
        """
        return f"<{self.__class__.__name__} id={getattr(self, 'id', None)!r}>"

    def __str__(self) -> str:
        """Краткое представление модели."""
        return self.__repr__()
