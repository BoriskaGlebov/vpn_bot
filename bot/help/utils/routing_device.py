from aiogram import Bot

from bot.core.config import settings_bot
from bot.help.utils.common_device import Device


class RoutingDevice(Device):
    """Базовый класс инструкции по добавлению профиля маршрутизации.

    Профиль маршрутизации — deeplink вида `<схема>://routing/add/<base64 JSON>`,
    который делит трафик: российские сайты идут напрямую, зарубежные — через VPN.
    Подклассы отличаются только константами (свой клиент — свой профиль,
    свои скриншоты), логика отправки общая.
    """

    CAPTION_SLEEP = 1.2

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет инструкции по добавлению профиля маршрутизации.

        Формат: вступительное сообщение с deeplink-ом профиля (`{link}`)
        внутри `<code>` — тап по блоку копирует ссылку в буфер, откуда её
        забирает кнопка вставки из буфера в приложении. Затем фото-шаги
        и финальное сообщение, где ссылка повторяется.

        Args:
            bot (Bot): Экземпляр бота Aiogram.
            chat_id (int): Telegram chat_id пользователя.

        Raises
            DeviceEmptyMessagesError: если для устройства не заданы подписи.
            DeviceEmptyMediaError: если в S3 не найдено ни одного файла.
            DeviceInstructionMismatchError: если количество подписей не
                соответствует количеству файлов.
            TelegramAPIError: при ошибке отправки сообщения в Telegram.

        """
        link = cls.LINK_PATH
        # `final_formatter` не передаём: по умолчанию он совпадает с
        # `intro_formatter`, а финалу нужна та же ссылка.
        await cls._send_intro_media_final(
            bot,
            chat_id,
            intro_formatter=lambda text: text.format(link=link),
        )


class RoutingHappDevice(RoutingDevice):
    """Профиль маршрутизации для клиента Happ."""

    PREFIX = f"{settings_bot.bucket.prefix}routing_happ/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.routing_happ
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.routing_happ


class RoutingIncyDevice(RoutingDevice):
    """Профиль маршрутизации для клиента INCY."""

    PREFIX = f"{settings_bot.bucket.prefix}routing_incy/"
    MESSAGES_PATH = settings_bot.messages.modes.help.instructions.routing_incy
    LINK_PATH = settings_bot.messages.modes.help.instructions.links.routing_incy
