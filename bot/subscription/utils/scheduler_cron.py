from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import bot
from bot.subscription.services import SubscriptionService

scheduler = AsyncIOScheduler()
service = SubscriptionService(bot=bot)


async def scheduled_check() -> None:
    """Запускает плановую проверку подписок пользователей.

    Функция вызывается по расписанию и инициирует проверку всех подписок,
    обновляя их статусы в зависимости от срока действия.

    Returns
        None

    """
    print("Запуск задачи по проверке подписок")
    await service.check_all_subscriptions()  # type: ignore [call-arg]
