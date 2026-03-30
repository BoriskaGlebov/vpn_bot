from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from loguru import logger

from bot.core.config import settings_bot
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.schemas import (
    AdminNotifyEventSchema,
    CheckAllSubscriptionsResponse,
    DeletedVPNConfigSchema,
    DeleteProxyEventSchema,
    DeleteVPNConfigsEventSchema,
    EventBase,
    SubscriptionEventSchema,
    UserNotifyEventSchema,
)
from bot.utils.start_stop_bot import send_to_admins
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_proxy import AmneziaProxy, AsyncDockerSSHClient
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG

m_subscription_local = settings_bot.messages.modes.subscription


@dataclass
class SubscriptionBotStats:
    """Агрегатор статистики проверки подписок.

    Класс используется для накопления и агрегации статистики как на уровне
    одного пользователя, так и для итоговой статистики по всем пользователям.

    Attributes
        checked: Количество обработанных пользователей.
        expired: Количество подписок, переведённых в истёкшие.
        notified: Количество отправленных уведомлений (пользователям и администраторам).
        configs_deleted: Количество удалённых VPN-конфигов.

    """

    checked: int = 0
    expired: int = 0
    notified: int = 0
    configs_deleted: int = 0

    def add(self, other: "SubscriptionBotStats") -> None:
        """Добавляет значения счётчиков из другого объекта статистики.

        Метод выполняет покомпонентное суммирование счётчиков и используется
        для агрегации статистики от отдельных обработчиков или пользователей.

        Args:
            other: Экземпляр `SubscriptionBotStats`, значения которого будут
                добавлены к текущему объекту.

        Returns
            None

        """
        self.checked += other.checked
        self.expired += other.expired
        self.notified += other.notified
        self.configs_deleted += other.configs_deleted


class SchedulerBotService:
    """Сервис бота для обработки событий планировщика подписок."""

    def __init__(self, adapter: SchedulerAPIAdapter, bot: Bot) -> None:
        """Инициализация класса планировщика.

        Args:
            adapter: Клиент для обращения к API планировщика.
            bot: Telegram bot instance для отправки сообщений.

        """
        self.api_adapter = adapter
        self.bot = bot

    async def _run_check_all(self) -> CheckAllSubscriptionsResponse:
        """Выполняет запрос к API планировщика и возвращает ответ."""
        return await self.api_adapter.check_all()

    async def _handle_delete_events(
        self, events: list[SubscriptionEventSchema]
    ) -> None:
        """Обрабатывает события, полученные от планировщика."""
        for event in events:
            if isinstance(event, DeleteVPNConfigsEventSchema):
                await self._trigger_config_deletion(event.user_id, event.configs)
            elif isinstance(event, DeleteProxyEventSchema):
                await self._trigger_proxy_deletion(event.user_id)
            else:
                # сюда можно логировать неизвестный event
                continue

    async def _handle_notify_events(
        self, events: list[SubscriptionEventSchema]
    ) -> None:
        """Обрабатывает события, полученные от планировщика."""
        for event in events:
            if isinstance(event, UserNotifyEventSchema):
                await self._send_user_message(event.user_id, event.message)
            elif isinstance(event, AdminNotifyEventSchema):
                await self._send_admin_message(event.message)
            else:
                # сюда можно логировать неизвестный event
                continue

    async def _send_user_message(
        self, tg_id: int, message: str, event: EventBase
    ) -> None:
        """Отправляет сообщение пользователю через бота."""
        try:
            if isinstance(event, UserNotifyEventSchema):
                user_text = ""
                if event.remaining_days >= 0 and event.active_sbs:
                    user_text = m_subscription_local.expire_subscription.soon.format(
                        type_subscription=event.subscription_type,
                        remaining=event.remaining_days,
                    )
                else:
                    user_text = m_subscription_local.expire_subscription.now.format(
                        type_subscription=event.subscription_type
                    )
                await self.bot.send_message(chat_id=tg_id, text=user_text)
            else:
                await self.bot.send_message(chat_id=tg_id, text=message)
        except TelegramForbiddenError:
            logger.error(
                "Невозможно отправить уведомление пользователю который заблокировал бота"
            )
            await send_to_admins(
                bot=self.bot,
                message_text=f"Невозможно отправить уведомление пользователю {tg_id} который заблокировал бота",
            )

    async def _trigger_config_deletion(
        self, tg_id: int, configs: list[DeletedVPNConfigSchema]
    ) -> None:
        """Триггер удаления VPN-конфигов через внешний сервис."""
        if not configs:
            return None

        async with ssh_lock:
            async with AsyncSSHClientWG(
                host=settings_bot.vpn_host,
                username=settings_bot.vpn_username,
            ) as ssh_client:
                for cfg in configs:
                    try:
                        await ssh_client.full_delete_user(public_key=cfg.pub_key)

                    except AmneziaError as e:
                        logger.error(f"SSH deletion error: {e}")
                        raise

    async def _trigger_proxy_deletion(self, tg_id: int) -> None:
        """Триггер удаления прокси через внешний сервис."""
        async with ssh_lock:
            async with AsyncDockerSSHClient(
                host=settings_bot.vpn_host,
                username=settings_bot.vpn_username,
                container=settings_bot.vpn_proxy,
            ) as client:
                proxy = AmneziaProxy(client=client, port=settings_bot.proxy_port)
                try:
                    res = await proxy.delete_user(username=str(tg_id))
                    if res:
                        await self._send_user_message(
                            tg_id=tg_id,
                            message="⚠️ Настройки прокси удалены.",
                        )
                except AmneziaError as e:
                    logger.error(f"SSH deletion error: {e}")
                    raise

    async def check_all_subscriptions(
        self,
    ) -> SubscriptionBotStats:
        """Проверяет все подписки пользователей и собирает статистику.

        Метод выполняет выборку всех пользователей с подгрузкой их подписок,
        роли и VPN-конфигов. Для каждого пользователя вызывается внутренний
        метод `_process_user`, который возвращает статистику по истёкшим
        подпискам, уведомлениям и удалённым конфигам.


        Returns
            SubscriptionStats: Статистика по всем пользователям. Ключи включают:
                - "checked": количество обработанных пользователей
                - "expired": количество истёкших подписок
                - "notified": количество отправленных уведомлений
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        result: CheckAllSubscriptionsResponse = await self._run_check_all()
        stats = SubscriptionBotStats(
            checked=result.stats.checked,
            expired=result.stats.expired,
            notified=0,
            configs_deleted=result.stats.configs_deleted,
        )
        print(result.events)
        for event in result.events:
            if isinstance(event, DeleteVPNConfigsEventSchema):
                await self._trigger_config_deletion(event.user_id, event.configs)
                text = m_subscription_local.expire_subscription.delete_configs_user
                await self._send_user_message(
                    tg_id=event.user_id, message=text, event=event
                )
                await send_to_admins(bot=self.bot, message_text=text)
            elif isinstance(event, DeleteProxyEventSchema):
                await self._trigger_proxy_deletion(event.user_id)
                stats.configs_deleted += 1

            # Обработка уведомлений
        for event in result.events:
            if isinstance(event, UserNotifyEventSchema):
                await self._send_user_message(
                    tg_id=event.user_id, message=event.message, event=event
                )
                stats.notified += 1
            elif isinstance(event, AdminNotifyEventSchema):
                await send_to_admins(bot=self.bot, message_text=event.message)
                stats.notified += 1
        await send_to_admins(
            bot=self.bot,
            message_text=m_subscription_local.daily_check.format(
                checked=stats.checked or 0,
                expired=stats.expired or 0,
                notified=stats.notified or 0,
                configs_deleted=stats.configs_deleted or 0,
            ),
        )
        return stats


#     async def _handle_expired(
#         self, session: AsyncSession, user: User, sub: Subscription
#     ) -> SubscriptionStats:
#         """Обрабатывает истёкшую подписку пользователя.
#
#         Если подписка активна, деактивирует её и отправляет уведомление пользователю.
#         Если подписка закончилась более чем на один день назад, удаляет все VPN-конфиги
#         пользователя и уведомляет администраторов.
#
#         Args:
#             session (AsyncSession): Асинхронная сессия SQLAlchemy.
#             user (User): Экземпляр пользователя.
#             sub (Subscription): Экземпляр подписки пользователя.
#
#         Returns
#             Dict[str, int]: Статистика по обработке с ключами:
#                 - "expired": количество истёкших подписок (0 или 1)
#                 - "notified": количество отправленных уведомлений (0 или 1)
#                 - "configs_deleted": количество удалённых VPN-конфигов
#
#         """
#         stats = SubscriptionStats()
#
#         if sub.is_active:
#             sub.is_active = False
#             stats.expired += 1
#             await self._send_user_message(
#                 message=m_subscription_local.expire_subscription.now.format(
#                     type_subscription=sub.type.value.upper()
#                 ),
#                 tg_id=user.telegram_id,
#             )
#             stats.notified += 1
#             await self._delete_proxy(user=user)
#
#         if sub.end_date:
#             delta = datetime.datetime.now(datetime.UTC) - sub.end_date
#             if delta.days >= 1:
#                 deleted = await self._delete_all_configs(session, user)
#                 if deleted:
#                     stats.configs_deleted += deleted
#                     await self._notify_admins_expired(user)
#
#         return stats
#
#     async def _handle_expiring_soon(
#         self, user: User, sub: Subscription
#     ) -> SubscriptionStats:
#         """Обрабатывает подписку, которая скоро истечет, и уведомляет пользователя.
#
#         Если до окончания подписки осталось 3 дня или меньше, отправляется
#         уведомление пользователю через бот.
#
#         Args:
#             user (User): Экземпляр пользователя.
#             sub (Subscription): Экземпляр подписки пользователя.
#
#         Returns
#             SubscriptionStats: Статистика по обработке с ключами:
#                 - "expired": всегда 0
#                 - "notified": количество отправленных уведомлений (0 или 1)
#                 - "configs_deleted": всегда 0
#
#         """
#         stats = SubscriptionStats()
#
#         remaining = sub.remaining_days()
#         if remaining is not None and remaining <= 3:
#             await self._send_user_message(
#                 message=m_subscription_local.expire_subscription.soon.format(
#                     remaining=remaining,
#                     type_subscription=sub.type.value.upper(),
#                 ),
#                 tg_id=user.telegram_id,
#             )
#
#             stats.notified += 1
#
#         return stats
#
#     async def _handle_unlimited_overuse(
#         self, session: AsyncSession, user: User
#     ) -> SubscriptionStats:
#         """Обрабатывает превышение лимита VPN-конфигов для пользователя.
#
#         Если количество VPN-конфигов пользователя превышает допустимый лимит
#         для текущей подписки, избыточные конфиги удаляются и администраторы
#         уведомляются об удалении.
#
#         Args:
#             session (AsyncSession): Асинхронная сессия SQLAlchemy.
#             user (User): Экземпляр пользователя.
#
#         Returns
#             SubscriptionStats: Статистика по обработке с ключами:
#                 - "expired": всегда 0
#                 - "notified": количество отправленных уведомлений администраторам (0 или >0)
#                 - "configs_deleted": количество удалённых VPN-конфигов
#
#         """
#         stats = SubscriptionStats()
#
#         sub = user.current_subscription
#         if not sub or not sub.is_active:
#             return stats
#
#         limit = DEVICE_LIMITS.get(sub.type) or 0
#         if limit <= 0:
#             return stats
#         elif len(user.vpn_configs) >= limit:
#             extra_cfgs = user.vpn_configs[: len(user.vpn_configs) - limit]
#
#             if not extra_cfgs:
#                 return stats
#
#             deleted = await self._delete_configs(session, user, extra_cfgs)
#             if deleted:
#                 stats.configs_deleted += deleted
#                 await self._notify_admins_expired(user)
#
#         return stats
#
#     async def _delete_configs(
#         self, session: AsyncSession, user: User, configs: list[VPNConfig]
#     ) -> int:
#         """Удаляет указанные VPN-конфиги пользователя и уведомляет его.
#
#         Метод подключается к удалённому серверу через SSH, удаляет конфиги
#         пользователя и удаляет их записи из базы данных. После успешного
#         удаления каждого конфига отправляется уведомление пользователю через бот.
#
#         Args:
#             session (AsyncSession): Асинхронная сессия SQLAlchemy.
#             user (User): Экземпляр пользователя.
#             configs (List[VPNConfig]): Список VPN-конфигов для удаления.
#
#         Raises
#             AmneziaError: В случае ошибки удаления через SSH.
#
#         Returns
#             int: Количество успешно удалённых VPN-конфигов.
#
#         """
#         if not configs:
#             return 0
#
#         deleted_count = 0
#
#         async with ssh_lock:
#             async with AsyncSSHClientWG(
#                 host=settings_bot.vpn_host,
#                 username=settings_bot.vpn_username,
#             ) as ssh_client:
#                 for cfg in configs:
#                     try:
#                         await ssh_client.full_delete_user(public_key=cfg.pub_key)
#                         await session.delete(cfg)
#                         deleted_count += 1
#
#                         await self._send_user_message(
#                             tg_id=user.telegram_id,
#                             message=m_subscription_local.expire_subscription.delete_unlimit_configs_user.format(
#                                 file_name=cfg.file_name,
#                             ),
#                         )
#
#                     except AmneziaError as e:
#                         self.logger.error(f"SSH deletion error: {e}")
#                         raise
#
#         return deleted_count
#

#     async def _delete_all_configs(self, session: AsyncSession, user: User) -> int:
#         """Удаляет все VPN-конфиги пользователя.
#
#         Вызывает внутренний метод `_delete_configs` для удаления всех конфигов
#         пользователя из базы данных.
#
#         Args:
#             session (AsyncSession): Асинхронная сессия SQLAlchemy.
#             user (User): Экземпляр пользователя.
#
#         Returns
#             int: Количество удалённых VPN-конфигов.
#
#         """
#         return await self._delete_configs(session, user, user.vpn_configs)
#
#     async def _notify_admins_expired(self, user: User) -> None:
#         """Отправляет уведомление администраторам о истёкшей подписке пользователя.
#
#         Метод формирует сообщение со статистикой пользователя и отправляет его
#         всем администраторам через бот.
#
#         Args:
#             user (User): Экземпляр пользователя, чья подписка истекла.
#
#         Returns
#             None
#
#         """
#         await send_to_admins(
#             bot=self.bot,
#             message_text=m_subscription_local.expire_subscription.admin_stats.format(
#                 tg_id=user.telegram_id,
#                 username=f"@{user.username}" or "-",
#                 first_name=user.first_name or "-",
#                 last_name=user.last_name or "-",
#             ),
#         )
#
#     @connection()
#     async def check_all_subscriptions(self, session: AsyncSession) -> SubscriptionStats:
#         """Проверяет все подписки пользователей и собирает статистику.
#
#         Метод выполняет выборку всех пользователей с подгрузкой их подписок,
#         роли и VPN-конфигов. Для каждого пользователя вызывается внутренний
#         метод `_process_user`, который возвращает статистику по истёкшим
#         подпискам, уведомлениям и удалённым конфигам.
#
#         Args:
#             session (AsyncSession): Асинхронная сессия SQLAlchemy.
#
#         Returns
#             SubscriptionStats: Статистика по всем пользователям. Ключи включают:
#                 - "checked": количество обработанных пользователей
#                 - "expired": количество истёкших подписок
#                 - "notified": количество отправленных уведомлений
#                 - "configs_deleted": количество удалённых VPN-конфигов
#
#         """
#         result = await session.execute(
#             select(User).options(
#                 selectinload(User.subscriptions),
#                 selectinload(User.role),
#                 selectinload(User.vpn_configs),
#             )
#         )
#         users = result.scalars().all()
#
#         stats = SubscriptionStats()
#         for user in users:
#             stats.checked += 1
#             user_stats = await self._process_user(session, user)
#             stats.add(user_stats)
#
#         await session.commit()
#         await send_to_admins(
#             bot=self.bot,
#             message_text=m_subscription_local.daily_check.format(
#                 checked=stats.checked or 0,
#                 expired=stats.expired or 0,
#                 notified=stats.notified or 0,
#                 configs_deleted=stats.configs_deleted or 0,
#             ),
#         )
#         return stats
#
#
# if __name__ == "__main__":
#     print(
#         m_subscription_local.expire_subscription.admin_stats.format(
#             tg_id=123,
#             username="user.username or ",
#             first_name="sdfsdf",
#             last_name="sdfsgs",
#         )
#     )
