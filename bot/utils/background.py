import asyncio
from collections.abc import Coroutine
from typing import Any

from loguru._logger import Logger

_tasks: set[asyncio.Task[Any]] = set()


def run_in_background(
    coro: Coroutine[Any, Any, Any], logger: Logger, error_message: str
) -> asyncio.Task[Any]:
    """Запускает корутину в фоне, не дожидаясь её завершения.

    Задача хранится в модульном множестве до завершения — иначе event loop
    держит её только через слабую ссылку, и сборщик мусора может собрать
    задачу до того, как она доработает. Необработанное исключение логируется
    явно, а не теряется молча.

    Args:
        coro: Корутина для запуска в фоне.
        logger: Логгер для необработанного исключения.
        error_message: Префикс сообщения в логе при падении задачи.

    Returns
        asyncio.Task[Any]: Запущенная фоновая задача.

    """
    task = asyncio.create_task(coro)
    _tasks.add(task)

    def _on_done(t: asyncio.Task[Any]) -> None:
        _tasks.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.exception(f"{error_message}: {exc}")

    task.add_done_callback(_on_done)
    return task
