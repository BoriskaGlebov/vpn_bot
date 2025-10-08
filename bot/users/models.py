from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from bot.database import Base, int_pk, str_null_true, str_uniq


class User(Base):
    """Модель пользователя, представляющая запись в таблице пользователей базы данных.

    Attributes
        id (int): Уникальный идентификатор пользователя.
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.
        username (Optional[str]): Имя пользователя в Telegram (необязательное поле).
        first_name (Optional[str]): Имя пользователя (необязательное поле).
        last_name (Optional[str]): Фамилия пользователя (необязательное поле).

    """

    id: Mapped[int_pk]
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str_uniq]
    first_name: Mapped[str_null_true]
    last_name: Mapped[str_null_true]


# class AuthGroup(Base):
#     """
#     Модель группы авторизации, представляющая запись в таблице групп авторизации базы данных.
#
#     Attributes:
#         id (int): Уникальный идентификатор группы.
#         name (str): Название группы (уникальное и не может быть пустым).
#         description (Optional[str]): Описание группы (необязательное поле).
#         is_active (bool): Флаг активности группы, по умолчанию True.
#     """
#
#     id: Mapped[int_pk]
#     name: Mapped[str_uniq]
#     description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
#     is_active: Mapped[bool] = mapped_column(Boolean, default=True)
#
#     # Двусторонняя связь с User
#     users = relationship(
#         "User",
#         secondary="user_auth_group",
#         back_populates="auth_groups",
#         lazy="selectin",
#     )
