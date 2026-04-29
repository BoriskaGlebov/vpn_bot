# bot/core/container.py
from aiogram import Bot

from bot.admin.adapter import AdminAPIAdapter
from bot.admin.services import AdminService

# from bot.ai.services.service import ChatService, build_chat_service
from bot.core.config import settings_bot, settings_db
from bot.integrations.api_client import APIClient
from bot.integrations.redis_client import RedisClient
from bot.news.adapter import NewsAPIAdapter
from bot.news.services import NewsService
from bot.redis_service import RedisAdminMessageStorage, RedisEmbeddingCache
from bot.referrals.adapter import ReferralAPIAdapter
from bot.referrals.services import ReferralService
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.services import SchedulerBotService
from bot.subscription.adapter import SubscriptionAPIAdapter
from bot.subscription.services import SubscriptionService
from bot.users.adapter import UsersAPIAdapter
from bot.users.services import UserService
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.services import VPNService
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter


class Container:
    """Контейнер зависимостей приложения.

    Отвечает за:
    - создание всех сервисов
    - связывание слоёв (API → adapters → services)
    - управление внешними ресурсами (Redis, HTTP client)

    Архитектура:
        APIClient → HTTP слой
        Adapters  → обёртки API
        Services  → бизнес-логика
        Redis     → кеш / временные данные
    """

    redis_manager: RedisClient
    api_client: APIClient
    xray_client: APIClient

    user_adapter: UsersAPIAdapter
    admin_adapter: AdminAPIAdapter
    subscription_adapter: SubscriptionAPIAdapter
    referral_adapter: ReferralAPIAdapter
    vpn_adapter: VPNAPIAdapter
    news_adapter: NewsAPIAdapter
    scheduler_adapter: SchedulerAPIAdapter
    xray_adapter: ThreeXUIAdapter

    user_service: UserService
    admin_service: AdminService
    subscription_service: SubscriptionService
    referral_service: ReferralService
    vpn_service: VPNService
    news_service: NewsService
    scheduler_bot_service: SchedulerBotService

    redis_admin_mess_storage: RedisAdminMessageStorage
    redis_embedding_cache: RedisEmbeddingCache

    # chat_service: ChatService | None

    def __init__(self, bot: Bot) -> None:
        """Инициализирует сервисы без асинхронных операций."""
        self.redis_manager = RedisClient(
            str(settings_db.redis_url), default_expire=settings_db.default_expire
        )
        self.api_client = APIClient(
            base_url=settings_bot.api_url, port=settings_bot.api_port
        )
        self.xray_client = APIClient(
            base_url=settings_bot.x_ray_base_url_panel,  # type: ignore[arg-type]
            port=settings_bot.x_ray_panel_port,
            scheme="https",
        )
        self.user_adapter = UsersAPIAdapter(client=self.api_client)
        self.admin_adapter = AdminAPIAdapter(client=self.api_client)
        self.subscription_adapter = SubscriptionAPIAdapter(client=self.api_client)
        self.referral_adapter = ReferralAPIAdapter(client=self.api_client)
        self.vpn_adapter = VPNAPIAdapter(client=self.api_client)
        self.news_adapter = NewsAPIAdapter(client=self.api_client)
        self.scheduler_adapter = SchedulerAPIAdapter(client=self.api_client)
        self.xray_adapter = ThreeXUIAdapter(
            api_client=self.xray_client, prefix=settings_bot.x_ray_panel_prefix
        )

        self.user_service = UserService(adapter=self.user_adapter)
        self.admin_service = AdminService(adapter=self.admin_adapter)
        self.referral_service = ReferralService(adapter=self.referral_adapter)
        self.subscription_service = SubscriptionService(
            adapter=self.subscription_adapter, user_adapter=self.user_adapter
        )
        self.vpn_service = VPNService(
            adapter=self.vpn_adapter,
            user_adapter=self.user_adapter,
            xray_adapter=self.xray_adapter,
        )
        self.news_service = NewsService(adapter=self.news_adapter)
        self.scheduler_bot_service = SchedulerBotService(
            bot=bot,
            adapter=self.scheduler_adapter,
            vpn_adapter=self.vpn_adapter,
            xray_adapter=self.xray_adapter,
        )

        self.redis_admin_mess_storage = RedisAdminMessageStorage(self.redis_manager)
        self.redis_embedding_cache = RedisEmbeddingCache(self.redis_manager)

        # self.chat_service: ChatService | None = None

    async def init(self) -> None:
        """Асинхронно инициализирует сервисы, требующие await."""
        await self.redis_manager.connect()
        # self.chat_service = await build_chat_service()

    async def shutdown(self) -> None:
        """Асинхронно завершает работу сервисов."""
        await self.redis_manager.disconnect()
        await self.api_client.close()
