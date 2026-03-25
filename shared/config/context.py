from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class LogUserContext:
    """Контекст пользователя для логирования.

    Attributes
        user (str | None): Строковое представление пользователя
            (например, username или tg_id).
        tg_id (int | None): Telegram ID пользователя.
        username (str | None): Username пользователя в Telegram.

    """

    user: str | None = None
    tg_id: int | None = None
    username: str | None = None


log_context: ContextVar[LogUserContext | None] = ContextVar(
    "log_context",
    default=None,
)


def patch_record(record: dict[str, Any]) -> bool:
    """Патчит запись логгера, добавляя данные пользователя из контекста.

    Функция используется в настройке loguru (через ``logger.configure`` или
    ``patcher``) для автоматического добавления пользовательских данных
    в поле ``record["extra"]``.

    Если контекст пользователя отсутствует, значения не добавляются.

    Args:
        record (dict[str, Any]): Запись лога, формируемая loguru.

    Returns
        bool: Всегда ``True`` для продолжения обработки записи логгером.

    """
    ctx = log_context.get()

    if ctx:
        record["extra"]["user"] = ctx.user or "undefined_user"
        record["extra"]["tg_id"] = ctx.tg_id
        record["extra"]["username"] = ctx.username

    return True
