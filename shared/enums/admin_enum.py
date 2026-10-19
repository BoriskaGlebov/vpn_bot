from enum import Enum


class RoleEnum(str, Enum):
    """Перечисление ролей пользователей.

    Раньше было два идентичных перечисления (RoleEnum и FilterTypeEnum —
    "роль" и "тип фильтра в админке" с одинаковым набором значений).
    Фильтр в админке — это и есть роль (плюс ALL для «без фильтра по
    роли»), отдельного понятия не было.
    """

    ADMIN = "admin"
    FOUNDER = "founder"
    USER = "user"
    ALL = "all"
