import asyncio
import time
from collections.abc import Callable

import aioboto3
from aiogram import Bot

from bot.app_error.base_error import (
    DeviceEmptyMediaError,
    DeviceEmptyMessagesError,
    DeviceInstructionMismatchError,
    DeviceMediaMismatchError,
)
from bot.core.config import settings_bot
from bot.help.keyboards.inline_kb import send_link_button


class Device:
    """Базовый класс устройств для отправки инструкций пользователю.

    Класс реализует общую логику:
    - получение файлов из S3-хранилища
    - отправку изображений с подписями
    - отправку кнопки со ссылкой (если задана)

    Подклассы должны определить:
        MESSAGES_PATH: list[str] — список caption для изображений
        LINK_PATH: str | None — ссылка на скачивание приложения (опционально)

    Используется как template-base класс для конкретных устройств
    (Android, iOS, Windows и т.д.). Подклассам с более сложным форматом
    (вступление + подписи + опциональное финальное сообщение, см. Split/Happ)
    следует переопределять `send_message`, используя `_send_intro_media_final`.

    Note:
        `HappDevice` — исключение: там `LINK_PATH` фактически `list[str]`
        (несколько ссылок под разные ОС), т.к. он не использует базовый
        `send_message`/`send_link_button`, а сам форматирует ссылки в тексте
        через `_send_intro_media_final`. Явно не переобъявляем тип атрибута
        в подклассе, чтобы не нарушать контракт базового класса.

    """

    PREFIX = settings_bot.bucket.prefix
    BUCKET_NAME = settings_bot.bucket.bucket_name
    MESSAGES_PATH: list[str]
    LINK_PATH: str | None
    CAPTION_SLEEP: float = 1.5

    @classmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
        """Отправляет пользователю серию инструкций с изображениями.

        Метод реализует общую логику отправки:
        - получает список файлов из S3-хранилища
        - отправляет изображения по порядку с подписями
        - при наличии ссылки отправляет кнопку скачивания приложения

        Подкласс должен определить:
            MESSAGES_PATH (list[str]): список caption для изображений
            LINK_PATH (str | None): ссылка на установку приложения (опционально)

        Args:
            bot (Bot): Экземпляр aiogram-бота.
            chat_id (int): Telegram chat_id пользователя.

        Raises
            DeviceMediaMismatchError: если количество файлов не совпадает
                с количеством подписей.
            TelegramAPIError: при ошибке отправки сообщения в Telegram.
            botocore.exceptions.ClientError: при ошибке обращения к S3.
            asyncio.TimeoutError: если запрос к хранилищу завис.

        """
        media = await cls._list_files()
        messages = cls.MESSAGES_PATH
        link = cls.LINK_PATH
        if len(media) != len(messages):
            raise DeviceMediaMismatchError(
                device=cls.__name__, media_len=len(media), messages_len=len(messages)
            )
        for file, caption in zip(media, messages):
            await bot.send_photo(
                chat_id=chat_id,
                photo=file,
                caption=caption.format(link=link),
                parse_mode="HTML",
            )
            await asyncio.sleep(cls.CAPTION_SLEEP)
        if link:
            await send_link_button(
                bot, chat_id, text="Скачайте приложение по ссылке:", url=link
            )

    @classmethod
    async def _send_intro_media_final(
        cls,
        bot: Bot,
        chat_id: int,
        *,
        intro_formatter: Callable[[str], str],
        caption_formatter: Callable[[str], str] = lambda text: text,
        final_formatter: Callable[[str], str] | None = None,
    ) -> None:
        """Отправляет вступление, серию фото с подписями и опциональный финал.

        Формат сообщений: `MESSAGES_PATH[0]` — вступительный текст,
        `MESSAGES_PATH[1:-1]` (или `[1:]`, если финала нет) — подписи к фото
        из `media` по порядку, `MESSAGES_PATH[-1]` — необязательное финальное
        сообщение (присутствует, если сообщений на одно больше, чем фото).

        Используется устройствами с более сложным форматом, чем базовый
        `send_message` (сейчас — Split, Happ), у которых конкретный способ
        подстановки ссылки в текст (`{link}` или позиционные `{}`) отличается,
        поэтому он передаётся явно через *_formatter колбэки.

        Args:
            bot (Bot): Экземпляр aiogram-бота.
            chat_id (int): Telegram chat_id пользователя.
            intro_formatter: Подставляет ссылку(и) во вступительный текст.
            caption_formatter: Подставляет ссылку(и) в подпись к фото
                (по умолчанию — без изменений).
            final_formatter: Подставляет ссылку(и) в финальное сообщение
                (по умолчанию совпадает с `intro_formatter`, если финал есть).

        Raises
            DeviceEmptyMessagesError: если для устройства не заданы подписи.
            DeviceEmptyMediaError: если в S3 не найдено ни одного файла.
            DeviceInstructionMismatchError: если количество подписей не
                соответствует количеству файлов (+1 вступление, +1 опционально финал).

        """
        media = await cls._list_files()
        messages = cls.MESSAGES_PATH

        if not messages:
            raise DeviceEmptyMessagesError(device=cls.__name__)
        if not media:
            raise DeviceEmptyMediaError(device=cls.__name__)
        if len(messages) not in {len(media) + 1, len(media) + 2}:
            raise DeviceInstructionMismatchError(
                cls.__name__, media=len(media), messages=len(messages)
            )

        await bot.send_message(
            chat_id, intro_formatter(messages[0]), disable_web_page_preview=True
        )
        has_final = len(messages) == len(media) + 2
        captions = messages[1:-1] if has_final else messages[1:]

        for file, caption in zip(media, captions):
            await bot.send_photo(
                chat_id=chat_id,
                photo=file,
                caption=caption_formatter(caption),
                parse_mode="HTML",
            )
            await asyncio.sleep(cls.CAPTION_SLEEP)

        if has_final:
            final_fmt = final_formatter or intro_formatter
            await bot.send_message(
                chat_id, final_fmt(messages[-1]), disable_web_page_preview=True
            )

    @classmethod
    async def _list_files(cls) -> list[str]:
        """Получает список файлов из S3-совместимого хранилища с полными URL.

        Метод использует настройки текущего класса (`cls.PREFIX` и `cls.BUCKET_NAME`)
        для обращения к бакету. Игнорирует “папки” (ключи, оканчивающиеся на `/`)
        и возвращает список файлов в виде полных URL, которые можно использовать,
        например, для отправки в Telegram.

        Returns
            list[str]: Список полных URL файлов в бакете.

        Raises
            botocore.exceptions.ClientError: Если при обращении к S3 возникает ошибка.
            asyncio.TimeoutError: Если операция занимает слишком много времени.

        """
        session = aioboto3.Session()
        async with session.client(
            "s3",
            endpoint_url=settings_bot.bucket.endpoint_url,
            aws_access_key_id=settings_bot.bucket.access_key.get_secret_value(),
            aws_secret_access_key=settings_bot.bucket.secret_key.get_secret_value(),
        ) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            files = []
            async for page in paginator.paginate(
                Bucket=cls.BUCKET_NAME, Prefix=cls.PREFIX
            ):
                for obj in page.get("Contents", []):
                    if not obj["Key"].endswith("/") and obj.get("Size", 0) > 0:
                        files.append(
                            f"{settings_bot.bucket.endpoint_url}/{settings_bot.bucket.bucket_name}/{obj['Key']}?ts={int(time.time())}"
                        )
            return files
