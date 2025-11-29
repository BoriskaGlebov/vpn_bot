import asyncio
import functools
from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, TypeVar

from aiogram import Bot, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.utils.chat_action import ChatActionSender
from loguru._logger import Logger

from bot.config import settings_bot

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
SelfT = TypeVar("SelfT", bound="BaseRouter")
m_error = settings_bot.MESSAGES.get("errors", {})


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

    async def counter_handler(self, command_key: str, state: FSMContext) -> int:
        """Увеличивает счётчик в FSM-контексте пользователя.

        Args:
            command_key (str): Ключ, под которым хранится счётчик в данных FSM.
            state (FSMContext): FSM-контекст пользователя.

        Returns
            int: Обновлённое значение счётчика.

        """
        data: dict[str, Any] = await state.get_data()
        counter_value: int = data.get(command_key, 0)
        counter_value += 1
        await state.update_data({command_key: counter_value})
        return counter_value

    @log_method
    async def mistake_handler_user(self, message: Message, state: FSMContext) -> None:
        """Обработчик некорректных сообщений от пользователя.

        Если пользователь вводит текст вместо кнопок, сообщение удаляется,
        и бот напоминает, что нужно использовать кнопки.

        Args:
            message (Message): Сообщение пользователя
            state (FSMContext): Текущее состояние пользователя

        Returns
            None

        """
        async with ChatActionSender.typing(bot=self.bot, chat_id=message.chat.id):
            try:
                await asyncio.sleep(2)
                await message.delete()
            except Exception as e:
                self.logger.error(e)
                pass

            current_state = await state.get_state()
            state_me = current_state.split(":")[1] if current_state else None
            if state_me:
                answer_text = m_error.get("unknown_command", "")
                counter = await self.counter_handler(command_key=state_me, state=state)
            if counter >= 2:
                await state.clear()

                user = message.from_user
                if user:
                    username = (
                        f"@{user.username}"
                        if user.username
                        else user.full_name or f"Гость_{user.id}"
                    )
                else:
                    username = "Гость"

                answer_text = m_error.get("help_limit_reached", "").format(
                    username=username
                )

                await message.answer(
                    text=answer_text, reply_markup=ReplyKeyboardRemove()
                )
            else:
                await message.answer(text=answer_text)

    @staticmethod
    def require_user(func: F) -> F:
        """Декоратор, проверяющий наличие пользователя в сообщении."""

        @functools.wraps(func)
        async def wrapper(
            self: SelfT, message: Message, *args: Any, **kwargs: Any
        ) -> Any:
            user = message.from_user
            if user is None:
                self.logger.error("message.from_user is None")
                return None
            return await func(self, message, *args, **kwargs)

        return wrapper
