import asyncio
import time

import aioboto3
from aiogram import Bot

from bot.config import settings_bucket
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
    (Android, iOS, Windows и т.д.).
    """

    PREFIX = settings_bucket.prefix
    BUCKET_NAME = settings_bucket.bucket_name
    MESSAGES_PATH: str
    LINK_PATH: str | None

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
            TelegramAPIError: при ошибке отправки сообщения в Telegram.
            botocore.exceptions.ClientError: при ошибке обращения к S3.
            asyncio.TimeoutError: если запрос к хранилищу завис.

        """
        media = await cls._list_files()
        messages = cls.MESSAGES_PATH
        link = cls.LINK_PATH
        if len(media) != len(messages):
            raise ValueError(
                f"{cls.__name__}: media ({len(media)}) != messages ({len(messages)})"
            )
        for file, caption in zip(media, messages):
            await bot.send_photo(
                chat_id=chat_id, photo=file, caption=caption, parse_mode="HTML"
            )
            await asyncio.sleep(1.5)
        if link:
            await send_link_button(
                bot, chat_id, text="Скачайте приложение по ссылке:", url=link
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
            endpoint_url=settings_bucket.endpoint_url,
            aws_access_key_id=settings_bucket.access_key.get_secret_value(),
            aws_secret_access_key=settings_bucket.secret_key.get_secret_value(),
        ) as s3:
            paginator = s3.get_paginator("list_objects_v2")
            files = []
            async for page in paginator.paginate(
                Bucket=cls.BUCKET_NAME, Prefix=cls.PREFIX
            ):
                for obj in page.get("Contents", []):
                    if not obj["Key"].endswith("/") and obj.get("Size", 0) > 0:
                        files.append(
                            f"{settings_bucket.endpoint_url}/{settings_bucket.bucket_name}/{obj['Key']}?ts={int(time.time())}"
                            # f"{settings_bucket.endpoint_url}/{settings_bucket.bucket_name}/{obj['Key']}"
                        )
            return files
