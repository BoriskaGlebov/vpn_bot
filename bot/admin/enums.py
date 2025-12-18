from enum import Enum


class ActionEnum(str, Enum):
    """Перечисление возможных действий с пользователем."""

    ROLE_CHANGE = "role_change"
    SUB_MANAGE = "sub_manage"
    ROLE_SELECT = "role_select"
    ROLE_CANCEL = "role_cancel"
    SUB_SELECT = "sub_select"
    SUBSCR_CANCEL = "subscr_cancel"
    NAVIGATE = "navigate"


class AdminModeKeys(str, Enum):
    """Ключи для шаблонов текста в админке."""

    USER = "user"
    EDIT_USER = "edit_user"


class FilterTypeEnum(str, Enum):
    """Перечисление типов фильтров пользователей."""

    ADMIN = "admin"
    FOUNDER = "founder"
    USER = "user"
