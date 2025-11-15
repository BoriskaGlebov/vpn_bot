from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru._logger import Logger

from bot.config import bot, logger
from bot.subscription.services import SubscriptionService

scheduler = AsyncIOScheduler()
service = SubscriptionService(bot=bot, logger=logger)


async def scheduled_check(logger: Logger) -> None:
    """Запускает плановую проверку подписок пользователей.

    Функция вызывается по расписанию и инициирует проверку всех подписок,
    обновляя их статусы в зависимости от срока действия.

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
            **stats,
            elapsed=elapsed,
        )

    except Exception as e:
        logger.exception(f"❌ Ошибка при проверке подписок: {e}")
