from abc import ABC, abstractmethod

from aiogram import Bot


class Device(ABC):
    """Абстрактный базовый класс для устройств, отправляющих сообщения пользователям.

    Этот класс определяет интерфейс для всех типов устройств (например,
    Android, iOS, PC, TV), которые должны реализовать метод `send_message`.

    """

    @abstractmethod
    async def send_message(self, bot: Bot, chat_id: int) -> None:
        """Отправляет сообщение в указанный чат.

        Этот метод должен быть реализован в подклассах для отправки
        определённого типа сообщения (текста, фото, видео и т.д.) с помощью
        экземпляра бота Aiogram.

        Args:
            bot (Bot): Экземпляр бота Aiogram, используемый для отправки сообщения.
            chat_id (int): Идентификатор чата Telegram, куда будет отправлено сообщение.

        Raises
            TelegramAPIError: Если при взаимодействии с Telegram API возникает ошибка.

        """
        ...
