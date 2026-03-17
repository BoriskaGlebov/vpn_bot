# bot/core/container.py

from bot.admin.services import AdminService
from bot.ai.services.service import ChatService, build_chat_service
from bot.config import bot, logger
from bot.news.services import NewsService
from bot.redis_manager import SettingsRedis, redis_manager
from bot.referrals.services import ReferralService
from bot.subscription.services import SubscriptionService
from bot.users.services import UserService
from bot.vpn.services import VPNService


class Container:
    """Контейнер для управления зависимостями приложения.

    Хранит все сервисы бота и обеспечивает их инициализацию/завершение работы.
    Позволяет переиспользовать единые экземпляры сервисов в aiogram и FastAPI.

    Attributes
        redis_manager (RedisManager): Менеджер соединений с Redis.
        user_service (UserService): Сервис для работы с пользователями.
        admin_service (AdminService): Сервис администрирования.
        referral_service (ReferralService): Сервис работы с реферальной системой.
        subscription_service (SubscriptionService): Сервис работы с подписками.
        vpn_service (VPNService): Сервис работы с VPN.
        news_service (NewsService): Сервис работы с новостями.
        chat_service (Optional[ChatService]): Сервис AI чат-бота (инициализируется асинхронно).

    """

    redis_manager: SettingsRedis
    user_service: UserService
    admin_service: AdminService
    referral_service: ReferralService
    subscription_service: SubscriptionService
    vpn_service: VPNService
    news_service: NewsService
    chat_service: ChatService | None

    def __init__(self) -> None:
        """Инициализирует сервисы без асинхронных операций."""
        self.redis_manager = redis_manager

        self.user_service = UserService(redis=self.redis_manager)
        self.admin_service = AdminService()
        self.referral_service = ReferralService(bot=bot, logger=logger)  # type: ignore[arg-type]
        self.subscription_service = SubscriptionService(bot=bot, logger=logger)  # type: ignore[arg-type]
        self.vpn_service = VPNService()
        self.news_service = NewsService(bot=bot, logger=logger)  # type: ignore[arg-type]

        self.chat_service: ChatService | None = None

    async def init(self) -> None:
        """Асинхронно инициализирует сервисы, требующие await."""
        await self.redis_manager.connect()
        self.chat_service = await build_chat_service()

    async def shutdown(self) -> None:
        """Асинхронно завершает работу сервисов."""
        await self.redis_manager.disconnect()
