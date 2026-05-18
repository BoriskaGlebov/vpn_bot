# bot/core/container.py
from aiogram import Bot

from bot.admin.adapter import AdminAPIAdapter
from bot.admin.services import AdminService

# from bot.ai.services.service import ChatService, build_chat_service
from bot.core.config import settings_bot
from bot.integrations.api_client import APIClient
from bot.integrations.redis_client import RedisClient
from bot.news.adapter import NewsAPIAdapter
from bot.news.services import NewsService
from bot.payment.adapter import PaymentAPIAdapter
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
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter, XRayRegistry


# TODO добавил новый адаптер
class Container:
    """DI-контейнер приложения.

    Отвечает за создание и связывание зависимостей:
    API-клиентов, адаптеров, сервисов и инфраструктуры (Redis, XRay).

    Архитектура
        APIClient:
            HTTP-клиент для backend API и XRay-панелей.

        Adapters:
            Обёртки над APIClient, инкапсулирующие HTTP-запросы.

        Services:
            Бизнес-логика, использующая адаптеры.

        Redis:
            Общий RedisClient для кеша и временных данных.

        XRayRegistry:
            Реестр XRay-нoд, создаётся из settings_bot.vpn.nodes.

    Attributes
        redis_manager (RedisClient): подключение к Redis.
        api_client (APIClient): клиент backend API.

        user_adapter (UsersAPIAdapter)
        admin_adapter (AdminAPIAdapter)
        subscription_adapter (SubscriptionAPIAdapter)
        payment_adapter (PaymentApiAdapter)
        referral_adapter (ReferralAPIAdapter)
        vpn_adapter (VPNAPIAdapter)
        news_adapter (NewsAPIAdapter)
        scheduler_adapter (SchedulerAPIAdapter)

        _xray_clients (list[APIClient]): HTTP-клиенты XRay (для shutdown).
        xray_adapters (XRayRegistry): реестр VPN/XRay нод.

        user_service (UserService)
        admin_service (AdminService)
        subscription_service (SubscriptionService)
        referral_service (ReferralService)
        vpn_service (VPNService)
        news_service (NewsService)
        scheduler_bot_service (SchedulerBotService)

        redis_admin_mess_storage (RedisAdminMessageStorage)
        redis_embedding_cache (RedisEmbeddingCache)

        bot (Bot): экземпляр aiogram Bot (используется в scheduler).

        chat_service (ChatService | None): отключён (в разработке).

    Notes
        - Конфигурация берётся из settings_bot (api, redis, vpn).
        - XRayRegistry инициализируется из settings_bot.vpn.nodes.
        - Каждый XRay node имеет собственный APIClient.
        - Все XRay APIClient закрываются в shutdown().
        - Redis подключается в init().

        Контейнер не содержит бизнес-логики и не выбирает VPN-ноды —
        он только создаёт их из конфигурации.

    """

    redis_manager: RedisClient
    api_client: APIClient

    user_adapter: UsersAPIAdapter
    admin_adapter: AdminAPIAdapter
    subscription_adapter: SubscriptionAPIAdapter
    payment_adapter: PaymentAPIAdapter
    referral_adapter: ReferralAPIAdapter
    vpn_adapter: VPNAPIAdapter
    news_adapter: NewsAPIAdapter
    scheduler_adapter: SchedulerAPIAdapter
    _xray_clients: list[APIClient]
    xray_adapters: XRayRegistry

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
        # 1. БАЗОВЫЕ КЛИЕНТЫ
        self.redis_manager = RedisClient(
            str(settings_bot.redis.url),
            default_expire=settings_bot.redis.default_expire,
        )
        self.api_client = APIClient(
            base_url=settings_bot.api.url, port=settings_bot.api.port
        )
        # 2. ADAPTERS API (обычные)
        self.user_adapter = UsersAPIAdapter(client=self.api_client)
        self.admin_adapter = AdminAPIAdapter(client=self.api_client)
        self.subscription_adapter = SubscriptionAPIAdapter(client=self.api_client)
        self.payment_adapter = PaymentAPIAdapter(client=self.api_client)
        self.referral_adapter = ReferralAPIAdapter(client=self.api_client)
        self.vpn_adapter = VPNAPIAdapter(client=self.api_client)
        self.news_adapter = NewsAPIAdapter(client=self.api_client)
        self.scheduler_adapter = SchedulerAPIAdapter(client=self.api_client)
        # 3. 🔥 ВОТ ЗДЕСЬ ВСТАВЛЯЕШЬ XRayRegistry
        xray_adapters: dict[str, ThreeXUIAdapter] = {}
        xray_clients: list[APIClient] = []
        for name, node in settings_bot.vpn.nodes.items():
            if node.xray is None:
                continue

            xray = node.require_xray()

            client = APIClient(
                base_url=xray.url_panel,  # type: ignore[arg-type]
                port=xray.panel_port,
                scheme="https",
            )
            xray_clients.append(client)

            xray_adapters[name] = ThreeXUIAdapter(
                api_client=client,
                prefix=xray.panel_prefix,
                correct_inbounds=xray.inbounds,
                username=xray.username.get_secret_value(),
                password=xray.password.get_secret_value(),
                host=xray.host,
                sub_port=xray.subscription_port,
                sub_prefix=xray.subscription_prefix,
                location_prefix=node.location_prefix,
            )

        self._xray_clients = xray_clients
        self.xray_adapters = XRayRegistry(xray_adapters)

        # 4. SERVICES
        self.user_service = UserService(adapter=self.user_adapter)
        self.admin_service = AdminService(adapter=self.admin_adapter)
        self.referral_service = ReferralService(adapter=self.referral_adapter)
        self.subscription_service = SubscriptionService(
            adapter=self.subscription_adapter,
            user_adapter=self.user_adapter,
            payment_adapter=self.payment_adapter,
        )
        self.vpn_service = VPNService(
            adapter=self.vpn_adapter,
            user_adapter=self.user_adapter,
            xray_registry=self.xray_adapters,
        )
        self.news_service = NewsService(adapter=self.news_adapter)
        self.scheduler_bot_service = SchedulerBotService(
            bot=bot,
            adapter=self.scheduler_adapter,
            vpn_adapter=self.vpn_adapter,
            xray_registry=self.xray_adapters,
        )

        # 5. REDIS
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
        for client in self._xray_clients:
            await client.close()
