from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import wraps
from typing import Annotated, Any, TypeVar, cast

from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from bot.config import settings_db

engine = create_async_engine(cast(str, settings_db.DATABASE_URL))

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

int_pk = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
created_at = Annotated[datetime, mapped_column(server_default=func.now())]
updated_at = Annotated[
    datetime, mapped_column(server_default=func.now(), onupdate=datetime.now)
]
str_uniq = Annotated[str, mapped_column(unique=True, nullable=False)]
str_null_true = Annotated[str, mapped_column(nullable=True)]

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def connection(isolation_level: str | None = None) -> Callable[[F], F]:
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
            async with async_session() as session:
                try:
                    if isolation_level:
                        await session.execute(
                            text(f"SET TRANSACTION ISOLATION LEVEL {isolation_level}")
                        )
                    return await method(*args, session=session, **kwargs)
                except Exception as e:
                    await session.rollback()
                    raise e
                finally:
                    await session.close()

        return wrapper  # type: ignore[return-value]

    return decorator


class Base(AsyncAttrs, DeclarativeBase):
    """Базовый класс для всех моделей базы данных.

    Предоставляет общие атрибуты и методы для всех моделей,
    включая автоматическое определение имени таблицы, поля даты создания
    и обновления записи, а также метод преобразования объекта в словарь.

    Attributes
        created_at (Mapped[datetime]): Дата и время создания записи.
        updated_at (Mapped[datetime]): Дата и время последнего обновления записи.

    """

    __abstract__ = True

    @declared_attr.directive
    def __tablename__(self) -> str:
        """Автоматически формирует имя таблицы в нижнем регистре с окончанием 's'.

        Returns
            str: Имя таблицы для модели.

        """
        return f"{self.__name__.lower()}s"

    created_at: Mapped[created_at]
    updated_at: Mapped[updated_at]

    def to_dict(self) -> dict[str, Any]:
        """Преобразует экземпляр модели в словарь.

        Ключи — имена колонок, значения — соответствующие данные.

        Returns
            dict[str, Any]: Словарь с данными модели.

        """
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
