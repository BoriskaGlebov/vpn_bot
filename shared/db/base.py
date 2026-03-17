from datetime import datetime
from typing import Annotated, Any

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

int_pk = Annotated[int, mapped_column(primary_key=True, autoincrement=True)]
created_at = Annotated[datetime, mapped_column(server_default=func.now())]
updated_at = Annotated[
    datetime, mapped_column(server_default=func.now(), onupdate=func.now())
]
str_uniq = Annotated[str, mapped_column(unique=True, nullable=False)]
str_null_true = Annotated[str, mapped_column(nullable=True)]


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
        return {c.name: getattr(self, c.name) for c in self.__mapper__.columns}
