import json
from collections.abc import Iterable
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.core.config import settings_bot
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.schemas import (
    AdminNotifyEventSchema,
    CheckAllSubscriptionsResponse,
    DeletedVPNConfigSchema,
    DeleteVPNConfigsEventSchema,
    EventBase,
    UserNotifyEventSchema,
)
from bot.utils.start_stop_bot import send_to_admins
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.router import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG, AsyncSSHClientWG2
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter

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


# TODO документацию
class SchedulerBotService:
    """Сервис бота для обработки событий планировщика подписок."""

    def __init__(
        self,
        adapter: SchedulerAPIAdapter,
        bot: Bot,
        vpn_adapter: VPNAPIAdapter,
        xray_adapter: ThreeXUIAdapter,
    ) -> None:
        """Инициализация класса планировщика.

        Args:
            adapter: Клиент для обращения к API планировщика.
            bot: Telegram bot instance для отправки сообщений.
            vpn_adapter: Клиента для обращения к API VPN
            xray_adapter: Адаптре для работы с 3xui панелью.

        """
        self.api_adapter = adapter
        self.vpn_adapter = vpn_adapter
        self.xray_adapter = xray_adapter
        self.bot = bot

    async def _run_check_all(self) -> CheckAllSubscriptionsResponse | None:
        """Выполняет запрос к API планировщика и возвращает ответ."""
        try:
            return await self.api_adapter.check_all()
        except APIClientError as exs:
            logger.error("️⚠️️  ️⚠️️  Произошла ошибка при плановой проверке подписок.")
            message_text = (
                f"️⚠️ ️⚠️ Произошла ошибка при плановой проверке подписок Планировщиком.\n\n"
                f"📌 {exs}"
            )
            await send_to_admins(bot=self.bot, message_text=message_text)
            return None

    async def _handle_delete_events(
        self, events: Iterable[DeleteVPNConfigsEventSchema]
    ) -> None:
        """Обрабатывает события, полученные от планировщика."""
        for event in events:
            if isinstance(event, DeleteVPNConfigsEventSchema):
                await self._trigger_config_deletion(
                    event.user_id, event.configs, [AsyncSSHClientWG, AsyncSSHClientWG2]
                )
            # elif isinstance(event, DeleteProxyEventSchema):
            #     await self._trigger_proxy_deletion(event.user_id)
            else:
                # сюда можно логировать неизвестный event
                continue

    async def _handle_notify_events(self, events: Iterable[EventBase]) -> None:
        """Обрабатывает события, полученные от планировщика."""
        for event in events:
            if isinstance(event, UserNotifyEventSchema):
                await self._send_user_message(event.user_id, event.message, event)
            elif isinstance(event, AdminNotifyEventSchema):
                await send_to_admins(bot=self.bot, message_text=event.message)
            else:
                # сюда можно логировать неизвестный event
                continue

    async def _send_user_message(
        self, tg_id: int, message: str, event: EventBase
    ) -> None:
        """Отправляет сообщение пользователю через бота."""
        try:
            if isinstance(event, UserNotifyEventSchema):
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

    async def _handle_broken_pipe(
        self, client_cls: AsyncSSHClientWG, error: Exception
    ) -> None:
        logger.error("SSH соединение разорвано ({}): {}", client_cls.__name__, error)

        await send_to_admins(
            bot=self.bot,
            message_text=(
                "⚠️ Не удалось подключиться к контейнеру\n"
                f"{client_cls.__name__}: {error}"
            ),
        )

    async def _handle_not_found(
        self, cfg: DeletedVPNConfigSchema, client_cls: AsyncSSHClientWG
    ) -> None:
        logger.warning("Не найден в {}: {}", client_cls.__name__, cfg.file_name)

        await send_to_admins(
            bot=self.bot,
            message_text=(
                "🔔 Требуется проверка.\n"
                f"Не найден в {client_cls.__name__}: {cfg.file_name}"
            ),
        )

    async def _delete_from_db(self, cfg: DeletedVPNConfigSchema) -> None:
        """Удаляет конфиг из БД."""
        logger.debug("Удаление из БД {}", cfg.file_name)

        try:
            res = await self.vpn_adapter.delete_config(
                file_name=cfg.file_name,
                pub_key=cfg.pub_key,
            )

            if res:
                logger.info("Удален из БД {}", cfg.file_name)

        except APIClientError as e:
            logger.error("Ошибка удаления из БД: {}", e)

    async def _fallback_delete_3xui(
        self,
        cfg: DeletedVPNConfigSchema,
    ) -> None:
        """Удаляет конфиг через 3x-ui если не найден в SSH."""
        logger.info("Fallback: проверка 3x-ui")

        try:
            all_configs = json.loads(cfg.pub_key)

            for config_id in all_configs:
                await self.xray_adapter.delete_config(
                    config_id=config_id,
                    inbounds=settings_bot.inbounds,
                )

        except json.JSONDecodeError:
            logger.error("Ошибка десериализации pub_key: {}", cfg.pub_key)
            raise

    async def _delete_from_ssh(
        self,
        cfg: DeletedVPNConfigSchema,
        ssh_clients: list[type[AsyncSSHClientWG]],
    ) -> bool:
        """Пытается удалить конфиг через SSH на всех клиентах."""
        for client_cls in ssh_clients:
            try:
                async with client_cls(
                    host=settings_bot.vpn_host,
                    username=settings_bot.vpn_username,
                ) as ssh_client:
                    if await ssh_client.full_delete_user(public_key=cfg.pub_key):
                        logger.info(
                            "Конфиг удален {} через {}",
                            cfg.file_name,
                            client_cls.__name__,
                        )
                        return True

                    await self._handle_not_found(cfg, client_cls)

            except AmneziaError as e:
                logger.error("SSH deletion error ({}): {}", client_cls.__name__, e)

            except BrokenPipeError as e:
                await self._handle_broken_pipe(client_cls, e)

        logger.info("Конфиг не найден ни на одном SSH сервере")
        return False

    async def _trigger_config_deletion(
        self,
        tg_id: int,
        configs: list[DeletedVPNConfigSchema],
        ssh_clients: list[type[AsyncSSHClientWG]],
    ) -> None:
        """Оркестрирует удаление VPN-конфигов."""
        if not configs:
            return

        async with ssh_lock:
            for cfg in configs:
                deleted = await self._delete_from_ssh(cfg, ssh_clients)

                if not deleted:
                    await self._fallback_delete_3xui(cfg)
                logger.info("Все возможные места проверил теперь удаляю.")
                await self._delete_from_db(cfg)

    async def _trigger_proxy_deletion(self, tg_id: int) -> None:
        """Триггер удаления прокси через внешний сервис."""
        # async with ssh_lock:
        #     async with AsyncDockerSSHClient(
        #         host=settings_bot.vpn_host,
        #         username=settings_bot.vpn_username,
        #         container=settings_bot.vpn_proxy,
        #     ) as client:
        #         proxy = AmneziaProxy(client=client, port=settings_bot.proxy_port)
        #         try:
        #             res = await proxy.delete_user(username=str(tg_id))
        #             if res:
        #                 await self._send_user_message(
        #                     tg_id=tg_id,
        #                     message="⚠️ Настройки прокси удалены.",
        #                 )
        #         except AmneziaError as e:
        #             logger.error(f"SSH deletion error: {e}")
        #             raise
        pass

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
        result = await self._run_check_all()
        stats = SubscriptionBotStats(
            checked=result.stats.checked if result else 0,
            expired=result.stats.expired if result else 0,
            notified=0,
            configs_deleted=0,
        )

        if not result:
            await send_to_admins(
                bot=self.bot,
                message_text=m_subscription_local.daily_check.format(
                    checked=stats.checked,
                    expired=stats.expired,
                    notified=stats.notified,
                    configs_deleted=stats.configs_deleted,
                ),
            )
            return stats

        delete_events: list[DeleteVPNConfigsEventSchema] = [
            e for e in result.events if isinstance(e, DeleteVPNConfigsEventSchema)
        ]

        notify_events: list[EventBase] = [
            e
            for e in result.events
            if isinstance(e, (UserNotifyEventSchema | AdminNotifyEventSchema))
        ]

        for event in delete_events:
            await self._trigger_config_deletion(
                event.user_id, event.configs, [AsyncSSHClientWG, AsyncSSHClientWG2]
            )
            stats.configs_deleted += len(event.configs)

            user_text = m_subscription_local.expire_subscription.delete_configs_user
            await self._send_user_message(
                tg_id=event.user_id, message=user_text, event=event
            )

            admin_text = m_subscription_local.expire_subscription.admin_stats.format(
                tg_id=event.user_id,
                username=f"@{event.username}",
                first_name=event.first_name,
                last_name=event.last_name,
                file_name="\n".join(cfg.file_name for cfg in event.configs),
            )
            await send_to_admins(bot=self.bot, message_text=admin_text)

        for n_event in notify_events:
            if isinstance(n_event, UserNotifyEventSchema):
                await self._send_user_message(
                    tg_id=n_event.user_id, message=n_event.message, event=n_event
                )
                stats.notified += 1
            elif isinstance(n_event, AdminNotifyEventSchema):
                await send_to_admins(bot=self.bot, message_text=n_event.message)
                stats.notified += 1

        await send_to_admins(
            bot=self.bot,
            message_text=m_subscription_local.daily_check.format(
                checked=stats.checked,
                expired=stats.expired,
                notified=stats.notified,
                configs_deleted=stats.configs_deleted,
            ),
        )
        return stats
