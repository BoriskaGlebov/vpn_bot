import asyncio
import functools
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

from aiogram import Bot, Router
from loguru._logger import Logger

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
SelfT = TypeVar("SelfT", bound="BaseRouter")


class BaseRouter(ABC):
    """Абстрактный базовый класс для всех роутеров проекта с логированием."""

    def __init__(self, bot: Bot, logger: Logger) -> None:
        self.bot = bot
        self.router = Router(name=self.__class__.__name__)
        self.logger = logger
        self._register_handlers()

    @abstractmethod
    def _register_handlers(self) -> None:
        """Регистрация всех хендлеров роутера."""
        pass

    @staticmethod
    def log_method(func: F) -> F:
        """Декоратор для логирования начала и конца выполнения метода."""
        if asyncio.iscoroutinefunction(func):
            # если функция асинхронная
            @functools.wraps(func)
            async def async_wrapper(self: SelfT, *args: Any, **kwargs: Any) -> Any:
                self.logger.info(
                    f"🚀 Начало: {self.__class__.__name__}.{func.__name__}"
                )
                try:
                    result = await func(self, *args, **kwargs)
                    self.logger.info(
                        f"✅ Успешно: {self.__class__.__name__}.{func.__name__}"
                    )
                    return result
                except Exception as e:
                    self.logger.exception(
                        f"❌ Ошибка в {self.__class__.__name__}.{func.__name__}: {e}"
                    )
                    raise

            return async_wrapper  # type: ignore[return-value]

        else:
            # если функция синхронная
            @functools.wraps(func)
            def sync_wrapper(self: SelfT, *args: Any, **kwargs: Any) -> Any:
                self.logger.info(
                    f"🚀 Начало: {self.__class__.__name__}.{func.__name__}"
                )
                try:
                    result = func(self, *args, **kwargs)
                    self.logger.info(
                        f"✅ Успешно: {self.__class__.__name__}.{func.__name__}"
                    )
                    return result
                except Exception as e:
                    self.logger.exception(
                        f"❌ Ошибка в {self.__class__.__name__}.{func.__name__}: {e}"
                    )
                    raise

            return sync_wrapper  # type: ignore[return-value]
