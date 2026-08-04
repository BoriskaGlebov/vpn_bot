import asyncio
from dataclasses import asdict
from datetime import datetime

from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.core.config import logger
from bot.scheduler.services import SchedulerBotService
from bot.utils.start_stop_bot import send_to_admins

scheduler = AsyncIOScheduler()


async def scheduled_check(
    service: SchedulerBotService,
) -> None:
    """Запускает плановую проверку подписок пользователей.

    Функция вызывается по расписанию и инициирует проверку всех подписок,
    обновляя их статусы в зависимости от срока действия. APScheduler не
    прокидывает исключения джобы никуда, кроме собственного логгера, поэтому
    здесь важно перехватить и залогировать/сообщить о любой ошибке самим —
    иначе сбой плановой проверки останется незамеченным.

    Args:
        service: Сервис планировщика, инкапсулирующий проверку подписок
            и рассылку уведомлений/удаление конфигов.

    """
    start_time = datetime.now()
    logger.info("⏰ Запуск плановой проверки подписок...")

    try:
        stats = await service.check_all_subscriptions()  # type: ignore
        elapsed = (datetime.now() - start_time).total_seconds()

        logger.success(
            "✅ Проверка подписок завершена. Пользователей: {checked}, истекло: {expired}, "
            "уведомлено: {notified}, конфигов удалено: {configs_deleted}. "
            "⏱ Время выполнения: {elapsed:.2f} сек.",
            **asdict(stats),
            elapsed=elapsed,
        )
        await asyncio.sleep(0.05)

    except TelegramForbiddenError as e:
        logger.exception(f"❌ Ошибка при проверке подписок: {e}")

    except Exception as e:
        logger.exception("❌ Непредвиденная ошибка плановой проверки подписок: {}", e)
        await send_to_admins(
            bot=service.bot,
            message_text=(
                "⚠️ Плановая проверка подписок упала с необработанной ошибкой.\n\n"
                f"📌 {type(e).__name__}: {e}"
            ),
        )
