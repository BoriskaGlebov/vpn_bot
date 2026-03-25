# bot/core/container.py
from bot.admin.adapter import AdminAPIAdapter
from bot.admin.services import AdminService

# from bot.ai.services.service import ChatService, build_chat_service
from bot.core.config import settings_bot
from bot.integrations.api_client import APIClient
from bot.integrations.redis_client import RedisClient, redis_manager
from bot.news.adapter import NewsAPIAdapter
from bot.news.services import NewsService
from bot.referrals.adapter import ReferralAPIAdapter
from bot.referrals.services import ReferralService
from bot.subscription.adapter import SubscriptionAPIAdapter

# from bot.referrals.services import ReferralService
from bot.subscription.services import SubscriptionService
from bot.users.adapter import UsersAPIAdapter
from bot.users.services import UserService
from bot.vpn.adapter import VPNAPIAdapter
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

    redis_manager: RedisClient
    user_service: UserService
    admin_service: AdminService
    referral_service: ReferralService
    subscription_service: SubscriptionService
    vpn_service: VPNService
    news_service: NewsService
    api_client: APIClient
    user_adapter: UsersAPIAdapter
    admin_adapter: AdminAPIAdapter
    subscription_adapter: SubscriptionAPIAdapter
    referral_adapter: ReferralAPIAdapter
    vpn_adapter: VPNAPIAdapter
    # chat_service: ChatService | None

    def __init__(self) -> None:
        """Инициализирует сервисы без асинхронных операций."""
        self.redis_manager = redis_manager
        self.api_client = APIClient(
            base_url=settings_bot.api_url, port=settings_bot.api_port
        )
        self.user_adapter = UsersAPIAdapter(client=self.api_client)
        self.admin_adapter = AdminAPIAdapter(client=self.api_client)
        self.subscription_adapter = SubscriptionAPIAdapter(client=self.api_client)
        self.referral_adapter = ReferralAPIAdapter(client=self.api_client)
        self.vpn_adapter = VPNAPIAdapter(client=self.api_client)
        self.news_adapter = NewsAPIAdapter(client=self.api_client)

        self.user_service = UserService(adapter=self.user_adapter)
        self.admin_service = AdminService(adapter=self.admin_adapter)
        self.referral_service = ReferralService(adapter=self.referral_adapter)
        self.subscription_service = SubscriptionService(
            adapter=self.subscription_adapter
        )
        self.vpn_service = VPNService(
            adapter=self.vpn_adapter, user_adapter=self.user_adapter
        )
        self.news_service = NewsService(adapter=self.news_adapter)

        # self.chat_service: ChatService | None = None

    async def init(self) -> None:
        """Асинхронно инициализирует сервисы, требующие await."""
        await self.redis_manager.connect()
        # self.chat_service = await build_chat_service()

    async def shutdown(self) -> None:
        """Асинхронно завершает работу сервисов."""
        await self.redis_manager.disconnect()
        await self.api_client.close()
