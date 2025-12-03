from abc import ABC, abstractmethod

import aioboto3
from aiogram import Bot

from bot.config import settings_bucket


class Device(ABC):
    """Абстрактный базовый класс для устройств, отправляющих сообщения пользователям.

    Этот класс определяет интерфейс для всех типов устройств (например,
    Android, iOS, PC, TV), которые должны реализовать метод `send_message`.

    """

    PREFIX = settings_bucket.prefix
    BUCKET_NAME = settings_bucket.bucket_name

    @classmethod
    @abstractmethod
    async def send_message(cls, bot: Bot, chat_id: int) -> None:
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

    @classmethod
    async def _list_files(cls) -> list[str]:
        """Получает список файлов из S3-совместимого хранилища с полными URL.

        Метод использует настройки текущего класса (`cls.PREFIX` и `cls.BUCKET_NAME`)
        для обращения к бакету. Игнорирует “папки” (ключи, оканчивающиеся на `/`)
        и возвращает список файлов в виде полных URL, которые можно использовать,
        например, для отправки в Telegram.

        Returns:
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
                    if not obj["Key"].endswith("/"):
                        files.append(
                            f"{settings_bucket.endpoint_url}/{settings_bucket.bucket_name}/{obj['Key']}"
                        )
            return files
