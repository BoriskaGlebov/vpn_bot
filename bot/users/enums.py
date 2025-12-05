from enum import Enum


class ChatType(str, Enum):
    """Типы чатов в Telegram."""

    PRIVATE = "private"
