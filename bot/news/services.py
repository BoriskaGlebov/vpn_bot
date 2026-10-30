import asyncio
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from loguru._logger import Logger

from bot.news.adapter import NewsAPIAdapter
from bot.redis_service import RedisNewsBroadcastStorage
from bot.utils.start_stop_bot import send_to_admins


class NewsService:
    """Сервис для работы с новостной рассылкой через Telegram-бота.

    Attributes
        bot (Bot): Экземпляр бота Aiogram.
        logger (Logger): Логгер Loguru для записи информации и ошибок.

    """

    def __init__(self, adapter: NewsAPIAdapter) -> None:
        self.api_adapter = adapter

    async def all_users_id(self) -> list[int]:
        """Получает список Telegram ID всех пользователей, кроме администраторов.

        Returns
            List[int]: Список Telegram ID пользователей для рассылки.

        """
        return await self.api_adapter.get_recipients()


class BroadcastService:
    """Переиспользуемая рассылка текстовых/медиа-сообщений списку получателей.

    Выделена из `bot.news.router.NewsRouter`, чтобы цикл рассылки (прогресс в
    Redis, FloodWait/`TelegramForbiddenError`, один итоговый отчёт вместо
    сообщения на каждую неудачу) не копировался отдельно для
    команды `/news` и для рассылки по выбранным пользователям из админки:
    у каждого вызывающего — свой `broadcast_storage` (разные ключи в
    Redis, чтобы параллельные рассылки не затирали прогресс друг друга) и свой
    заголовок итогового отчёта.

    Args:
        bot: Экземпляр бота Aiogram.
        logger: Логгер Loguru.
        broadcast_storage: Хранение прогресса этой рассылки — позволяет
            возобновить её после рестарта процесса.
        summary_title: Заголовок итогового отчёта админам, отличает рассылку
            новостей от рассылки по выбранным пользователям.

    """

    def __init__(
        self,
        bot: Bot,
        logger: Logger,
        broadcast_storage: RedisNewsBroadcastStorage,
        summary_title: str,
    ) -> None:
        self.bot = bot
        self.logger = logger
        self.broadcast_storage = broadcast_storage
        self.summary_title = summary_title

    @staticmethod
    def _format_id_list(ids: list[int], limit: int = 5) -> str:
        """Форматирует список id для отчёта: первые `limit` + "и ещё N"."""
        if not ids:
            return ""
        head = ", ".join(str(i) for i in ids[:limit])
        rest = len(ids) - limit
        return f"{head} и ещё {rest}" if rest > 0 else head

    def _format_broadcast_summary(
        self,
        sent: int,
        forbidden_ids: list[int],
        bad_request_ids: list[int],
        other_ids: list[int],
        preview: str | None = None,
    ) -> str:
        """Собирает один итоговый отчёт админам вместо сообщения на каждую неудачу.

        На базе с заметной долей заблокировавших бота цикл рассылки
        иначе превращается в сотни отдельных сообщений админам.
        """
        failed = len(forbidden_ids) + len(bad_request_ids) + len(other_ids)
        lines = [f"{self.summary_title} завершена."]
        if preview:
            lines.append(f"Текст: {preview}")
        lines += [
            f"Доставлено: {sent}",
            f"Не доставлено: {failed}",
        ]
        if forbidden_ids:
            lines.append(
                f"— заблокировали бота ({len(forbidden_ids)}): "
                f"{self._format_id_list(forbidden_ids)}"
            )
        if bad_request_ids:
            lines.append(
                f"— TelegramBadRequest ({len(bad_request_ids)}): "
                f"{self._format_id_list(bad_request_ids)}"
            )
        if other_ids:
            lines.append(
                f"— прочие ошибки ({len(other_ids)}): {self._format_id_list(other_ids)}"
            )
        return "\n".join(lines)

    async def send_message(self, user_id: int, content: dict[str, Any]) -> None:
        """Отправляет одно сообщение пользователю по его типу (текст/фото/видео)."""
        if content["content_type"] == "text":
            await self.bot.send_message(user_id, content["text"])

        elif content["content_type"] == "photo":
            await self.bot.send_photo(
                user_id,
                photo=content["photo_file_id"],
                caption=content["caption"],
            )
        elif content["content_type"] == "video":
            await self.bot.send_video(
                user_id,
                video=content["video_file_id"],
                caption=content["caption"],
            )

    async def broadcast_to_all(
        self,
        content: dict[str, Any],
        recipients: list[int],
        initiated_by: str,
        preview: str | None = None,
        notify_always: bool = False,
    ) -> tuple[int, int]:
        """Рассылает сообщение всем `recipients`, сохраняя прогресс в Redis.

        Прогресс (кому сообщение ещё не доставлено) пишется в
        `broadcast_storage` перед циклом и обновляется после каждого
        получателя, а очищается только по завершении. Если процесс
        упадёт или будет передеплоен в середине, оставшиеся получатели
        не потеряются — `resume_pending_broadcast` подхватит их при
        следующем старте.

        Args:
            content: Данные сообщения (тип контента, текст/медиа).
            recipients: Telegram ID получателей, которым сообщение
                ещё не доставлено.
            initiated_by: Кто инициировал рассылку — имя админа или
                "restart-resume" при возобновлении после рестарта (для логов).
            preview: Текст рассылки для итогового отчёта админам (например,
                чтобы отличить, какая именно рассылка завершилась). `None` —
                в отчёт текст не включается (так ведёт себя рассылка новостей).
            notify_always: Слать итоговый отчёт даже без единой неудачи — для
                рассылки по выбранным пользователям это единственный способ
                узнать результат (HTTP-ответ админке уходит до завершения).

        Returns
            tuple[int, int]: (отправлено, не отправлено).

        """
        self.logger.bind(user=initiated_by).info(
            f"Начата рассылка, получателей: {len(recipients)}, "
            f"тип: {content['content_type']}"
        )
        remaining = list(recipients)
        await self.broadcast_storage.save(news=content, recipients=remaining)

        sent = 0
        failed = 0
        forbidden_ids: list[int] = []
        bad_request_ids: list[int] = []
        other_ids: list[int] = []

        for user_id in list(remaining):
            try:
                await self.send_message(user_id, content)
                sent += 1

            except TelegramRetryAfter as e:
                self.logger.warning(f"FloodWait {e.retry_after}s для {user_id}, жду...")
                await asyncio.sleep(e.retry_after)
                try:
                    await self.send_message(user_id, content)
                    sent += 1
                except Exception as exc:
                    failed += 1
                    other_ids.append(user_id)
                    self.logger.exception(
                        f"Повторная отправка не удалась {user_id}: {exc}"
                    )

            except TelegramForbiddenError:
                failed += 1
                forbidden_ids.append(user_id)
                self.logger.warning(
                    f"Пользователь {user_id} заблокировал бота, пропускаем."
                )

            except TelegramBadRequest as e:
                failed += 1
                bad_request_ids.append(user_id)
                self.logger.warning(f"Ошибка TelegramBadRequest для {user_id}: {e}")
            except Exception as exc:
                failed += 1
                other_ids.append(user_id)
                self.logger.exception(
                    f"Неизвестная ошибка при отправке {user_id}: {exc}"
                )

            remaining.remove(user_id)
            await self.broadcast_storage.update_recipients(remaining)
            await asyncio.sleep(0.05)

        await self.broadcast_storage.clear()
        self.logger.bind(user=initiated_by).info(
            f"Рассылка завершена. Отправлено: {sent}, ошибок: {failed}"
        )
        if failed or notify_always:
            await send_to_admins(
                bot=self.bot,
                message_text=self._format_broadcast_summary(
                    sent=sent,
                    forbidden_ids=forbidden_ids,
                    bad_request_ids=bad_request_ids,
                    other_ids=other_ids,
                    preview=preview,
                ),
            )
        return sent, failed

    async def resume_pending_broadcast(self) -> None:
        """Возобновляет рассылку, прерванную рестартом или падением процесса.

        Вызывается один раз при старте бота. Если в Redis остался
        незавершённый прогресс рассылки — отправляет сообщение
        оставшимся получателям, не дожидаясь, пока админ заметит и
        запустит рассылку заново (что продублировало бы доставку тем,
        кто уже получил сообщение).
        """
        data = await self.broadcast_storage.get()
        if not data:
            return
        news = data.get("news")
        recipients = data.get("recipients") or []
        if not news or not recipients:
            await self.broadcast_storage.clear()
            return
        self.logger.warning(
            f"Найдена прерванная рассылка, осталось "
            f"{len(recipients)} получателей — возобновляю"
        )
        await self.broadcast_to_all(news, recipients, initiated_by="restart-resume")
