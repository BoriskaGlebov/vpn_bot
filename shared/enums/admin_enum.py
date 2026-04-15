from enum import Enum


class FilterTypeEnum(str, Enum):
    """Перечисление типов фильтров пользователей."""

    ADMIN = "admin"
    FOUNDER = "founder"
    USER = "user"
    ALL = "all"


class RoleEnum(str, Enum):
    """Перечисление ролей пользователей."""

    ADMIN = "admin"
    FOUNDER = "founder"
    USER = "user"
