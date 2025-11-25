from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru._logger import Logger

from bot.config import bot, logger
from bot.subscription.services import SubscriptionService

scheduler = AsyncIOScheduler()
service = SubscriptionService(bot=bot, logger=logger)  # type: ignore[arg-type]


async def scheduled_check(logger: Logger) -> None:
    pass
