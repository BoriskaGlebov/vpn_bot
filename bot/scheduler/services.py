import json
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import VPNConfigDeletionFailedError
from bot.core.config import settings_bot
from bot.scheduler.adapter import SchedulerAPIAdapter
from bot.scheduler.enums import DeleteStatus
from bot.scheduler.schemas import (
    AdminNotifyEventSchema,
    CheckAllSubscriptionsResponse,
    DeletedVPNConfigSchema,
    DeleteVPNConfigsEventSchema,
    EventBase,
    UserNotifyEventSchema,
)
from bot.users.enums import PremiumLocation, available_locations
from bot.utils.start_stop_bot import send_to_admins
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.services import ssh_lock
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG, AsyncSSHClientWG2
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter, XRayRegistry

m_subscription_local = settings_bot.messages.modes.subscription
# available_locations() (не Location) — иначе перебор попадёт на локацию без
# реально сконфигурированной ноды (например "fi", пока она отключена) и
# settings_bot.vpn.get()/xray_registry.get() ниже упадут с исключением.
ALL_LOCATIONS = (*available_locations(), *PremiumLocation)


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

    def __init__(
        self,
        adapter: SchedulerAPIAdapter,
        bot: Bot,
        vpn_adapter: VPNAPIAdapter,
        xray_registry: XRayRegistry,
    ) -> None:
        """Инициализация класса планировщика.

        Args:
            adapter: Клиент для обращения к API планировщика.
            bot: Telegram bot instance для отправки сообщений.
            vpn_adapter: Клиента для обращения к API VPN
            xray_registry: Адаптеры для работы с 3xui панелью.

        """
        self.api_adapter = adapter
        self.vpn_adapter = vpn_adapter
        self.xray_registry = xray_registry
        self.bot = bot

    async def _run_check_all(self) -> CheckAllSubscriptionsResponse | None:
        """Выполняет запрос к API планировщика и возвращает ответ.

        При ошибке API уведомляет админов и возвращает None — вызывающий код
        (`check_all_subscriptions`) не должен уведомлять их повторно.

        Returns
            CheckAllSubscriptionsResponse | None: Ответ API, либо None,
                если запрос завершился `APIClientError`.

        """
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

    async def _send_user_message(
        self, tg_id: int, message: str, event: EventBase
    ) -> None:
        """Отправляет сообщение пользователю через бота.

        Для `UserNotifyEventSchema` текст формируется из шаблонов
        уведомления об истечении подписки (`message` игнорируется); для
        остальных типов событий отправляется `message` как есть. Если
        пользователь заблокировал бота — уведомляет админов вместо падения.

        Args:
            tg_id: Telegram ID получателя.
            message: Текст сообщения (используется, если событие — не
                `UserNotifyEventSchema`).
            event: Исходное событие, определяющее формат текста.

        """
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
            # Штатная, регулярно встречающаяся ситуация (пользователь
            # заблокировал бота), а не сбой планировщика — поэтому warning,
            # а не error.
            logger.warning(
                "Невозможно отправить уведомление tg_id={} (пользователь заблокировал бота)",
                tg_id,
            )
            await send_to_admins(
                bot=self.bot,
                message_text=f"Невозможно отправить уведомление пользователю {tg_id} который заблокировал бота",
            )

    async def _handle_broken_pipe(
        self,
        client_cls: AsyncSSHClientWG | type[AsyncSSHClientWG],
        file_name: str,
        error: Exception,
    ) -> None:
        """Логирует обрыв SSH-соединения при удалении конфига.

        Args:
            client_cls: SSH-клиент, на котором произошёл обрыв — инстанс,
                если соединение успело открыться, либо класс клиента, если
                обрыв случился ещё на этапе подключения.
            file_name: Имя файла конфига, который пытались удалить.
            error: Исходное исключение `BrokenPipeError`.

        """
        logger.error(
            "SSH соединение разорвано при удалении {} ({}): {}",
            file_name,
            str(client_cls),
            error,
        )

        # await send_to_admins(
        #     bot=self.bot,
        #     message_text=(
        #         f"⚠️ Не удалось подключиться к контейнеру\n{str(client_cls)}: {error}\n"
        #         f"Когда удалял файл - <b>{file_name}</b>"
        #     ),
        # )

    async def _handle_xray_error(
        self,
        client_cls: ThreeXUIAdapter,
        error: Exception,
        config_id: str,
        serv_loc: str,
    ) -> None:
        """Логирует и уведомляет админов об ошибке запроса к 3x-ui панели.

        Args:
            client_cls: Адаптер `ThreeXUIAdapter`, на котором произошла ошибка.
            error: Исходное исключение (`APIClientError`).
            config_id: Идентификатор конфига, который пытались удалить.
            serv_loc: Локация/сервер, на котором произошла ошибка.

        """
        logger.error(
            "Ошибка при осуществлении запроса к XRAY панели: ({}): {}",
            str(client_cls),
            error,
        )

        await send_to_admins(
            bot=self.bot,
            message_text=(
                f"⚠️ Ошибка удаления config_id={config_id} в {serv_loc}: {error}\n\n"
                f"ThreeXUIAdapter - {client_cls}"
            ),
        )

    async def _notify_deletion_failed(self, cfg: DeletedVPNConfigSchema) -> None:
        """Уведомляет админов, что конфиг не удалось удалить ни на Amnezia, ни на 3x-ui.

        Запись в БД в этом случае намеренно не трогается (см.
        `VPNConfigDeletionFailedError`) — конфиг может реально существовать
        на одном из серверов, и попытка удаления повторится в следующем
        прогоне планировщика.

        Args:
            cfg: Данные конфига, который не удалось удалить.

        """
        error = VPNConfigDeletionFailedError(cfg.file_name)
        envelope = error.to_envelope()
        logger.error(
            "[{}] {} | details={}",
            envelope.error.code,
            envelope.error.message,
            envelope.error.details,
        )
        await send_to_admins(bot=self.bot, message_text=f"⚠️ {envelope.error.message}")

    async def _delete_from_db(self, cfg: DeletedVPNConfigSchema) -> None:
        """Удаляет запись о конфиге из БД через `api/`.

        Вызывается только после того, как конфиг подтверждённо удалён (или
        точно не найден) на внешнем сервисе (Amnezia/3x-ui) — см.
        `_trigger_config_deletion`.

        Args:
            cfg: Данные конфига, чью запись нужно удалить из БД.

        """
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
    ) -> DeleteStatus:
        """Удаляет конфиг через панели 3x-ui, если не найден/не удалён по SSH.

        `cfg.pub_key` в этом сценарии — не WG-публичный ключ, а JSON-список
        `config_id` в 3x-ui (перегрузка одного поля под два бэкенда, см.
        `DeletedVPNConfigSchema`). Перебирает все локации (`ALL_LOCATIONS`) и
        удаляет там все `config_id` из списка.

        Args:
            cfg: Данные удаляемого конфига; `pub_key` ожидается как
                JSON-массив идентификаторов конфигов в 3x-ui.

        Returns
            DeleteStatus: `DELETED`, если все config_id успешно удалены в
                какой-то одной локации; `NOT_FOUND`, если ошибок не было, но
                удалить нечего; `ERROR`, если `pub_key` не распарсился как
                JSON или удаление хотя бы одного config_id завершилось ошибкой.

        """
        logger.info("Fallback: проверка 3x-ui")
        deletion_statistic = []
        try:
            all_configs = json.loads(cfg.pub_key)
            for serv_loc in ALL_LOCATIONS:
                adapter = self.xray_registry.get(
                    serv_loc.value if serv_loc.name.lower() != "main" else "main"
                )
                results = []
                for config_id in all_configs:
                    try:
                        is_deleted = await adapter.delete_config(config_id=config_id)
                        results.append(is_deleted)

                    except APIClientError as e:
                        logger.warning(
                            "Ошибка удаления config_id={} в {}: {}",
                            config_id,
                            serv_loc,
                            e,
                        )
                        results.append(False)
                        deletion_statistic.append(DeleteStatus.ERROR)
                        await self._handle_xray_error(
                            client_cls=adapter,
                            error=e,
                            config_id=config_id,
                            serv_loc=serv_loc,
                        )

                if all(results):
                    return DeleteStatus.DELETED

            return (
                DeleteStatus.NOT_FOUND
                if DeleteStatus.ERROR not in deletion_statistic
                else DeleteStatus.ERROR
            )

        except json.JSONDecodeError:
            logger.error("Ошибка десериализации pub_key: {}", cfg.pub_key)
            return DeleteStatus.ERROR

    async def _delete_from_ssh(
        self,
        cfg: DeletedVPNConfigSchema,
        ssh_clients: list[type[AsyncSSHClientWG]],
    ) -> DeleteStatus:
        """Пытается удалить конфиг через SSH на всех Amnezia-клиентах и локациях.

        Перебирает все переданные классы SSH-клиентов и все локации
        (`ALL_LOCATIONS`), пока конфиг не будет удалён либо не закончатся
        варианты подключения.

        Args:
            cfg: Данные удаляемого VPN-конфига (имя файла и публичный ключ).
            ssh_clients: Классы SSH-клиентов, которые нужно перебрать
                (например, `AsyncSSHClientWG`, `AsyncSSHClientWG2`).

        Returns
            DeleteStatus: `DELETED`, если конфиг удалён хотя бы одним клиентом;
                `NOT_FOUND`, если ни на одном сервере не было ошибок, но конфиг
                нигде не найден; `ERROR`, если хотя бы одна попытка завершилась
                ошибкой подключения.

        """
        deletion_statistic = []
        for client_cls in ssh_clients:
            for loc_prefix in ALL_LOCATIONS:
                if loc_prefix.name.lower() == "main":
                    server_info = settings_bot.vpn.get("main")
                else:
                    server_info = settings_bot.vpn.get(loc_prefix.value)
                ssh_client: AsyncSSHClientWG | None = None
                try:
                    async with client_cls(
                        host=server_info.host,
                        username=server_info.username,
                        use_local=server_info.use_local,
                        location_prefix=server_info.location_prefix,
                    ) as ssh_client:
                        result = await ssh_client.full_delete_user(
                            public_key=cfg.pub_key
                        )
                        if result:
                            logger.info(
                                "Конфиг удален {} через {}",
                                cfg.file_name,
                                client_cls.__name__,
                            )
                            return DeleteStatus.DELETED

                except AmneziaError as e:
                    logger.error("SSH deletion error ({}): {}", client_cls.__name__, e)
                    deletion_statistic.append(DeleteStatus.ERROR)

                except BrokenPipeError as e:
                    # ssh_client может быть не присвоен, если BrokenPipeError
                    # произошёл на этапе подключения (до входа в `async with`).
                    await self._handle_broken_pipe(
                        ssh_client or client_cls, cfg.file_name, e
                    )
                    deletion_statistic.append(DeleteStatus.ERROR)
        else:
            return (
                DeleteStatus.NOT_FOUND
                if DeleteStatus.ERROR not in deletion_statistic
                else DeleteStatus.ERROR
            )

    async def _trigger_config_deletion(
        self,
        tg_id: int,
        configs: list[DeletedVPNConfigSchema],
        ssh_clients: list[type[AsyncSSHClientWG]],
    ) -> int:
        """Оркестрирует последовательное удаление VPN-конфигов пользователя.

        Для каждого конфига сначала пробует удалить его через SSH (Amnezia),
        затем, если там не нашлось или произошла ошибка — через панель 3x-ui.
        Из БД конфиг удаляется только если он реально удалён (или точно
        не найден) хотя бы в одном из внешних сервисов; если оба сервиса
        вернули ошибку — запись в БД намеренно не трогается, а админы
        получают уведомление (см. `_notify_deletion_failed`).

        Args:
            tg_id: Telegram ID пользователя, которому принадлежат конфиги.
            configs: Список конфигов на удаление.
            ssh_clients: Классы SSH-клиентов для перебора в `_delete_from_ssh`.

        Returns
            int: Количество фактически удалённых конфигов.

        """
        if not configs:
            return 0
        count_deleted = 0
        async with ssh_lock:
            for cfg in configs:
                ssh_status = await self._delete_from_ssh(cfg, ssh_clients)

                if ssh_status == DeleteStatus.DELETED:
                    await self._delete_from_db(cfg)
                    count_deleted += 1
                    continue
                if ssh_status == DeleteStatus.ERROR:
                    logger.error("SSH ошибка → НЕ удаляю из БД {}", cfg.file_name)

                if ssh_status in (DeleteStatus.NOT_FOUND, DeleteStatus.ERROR):
                    logger.info(f"Файл не найден в Amnezia {cfg.file_name} ищу в 3x-ui")
                    xray_status = await self._fallback_delete_3xui(cfg)

                    if xray_status == DeleteStatus.DELETED:
                        logger.success(f"Удалил файл в панели 3x-ui {cfg.file_name}")
                        await self._delete_from_db(cfg)
                        count_deleted += 1
                        continue
                    elif (
                        xray_status == DeleteStatus.NOT_FOUND
                        and ssh_status == DeleteStatus.NOT_FOUND
                    ):
                        logger.warning(f"Не нашел файл в панели 3x-ui {cfg.file_name}")
                        await self._delete_from_db(cfg)
                        count_deleted += 1
                        continue
                    else:
                        await self._notify_deletion_failed(cfg)
            return count_deleted

    async def check_all_subscriptions(
        self,
    ) -> SubscriptionBotStats:
        """Проверяет все подписки пользователей и собирает статистику.

        Дёргает `/scheduler/check-all` (через `_run_check_all`), который на
        стороне `api/` деактивирует истёкшие подписки и формирует список
        событий. Затем разбирает события на два потока: удаление VPN-конфигов
        (`DeleteVPNConfigsEventSchema` → `_trigger_config_deletion`) и
        уведомления (`UserNotifyEventSchema`/`AdminNotifyEventSchema` →
        `_send_user_message`/`send_to_admins`). В конце шлёт админам сводную
        статистику прогона.

        Returns
            SubscriptionStats: Статистика по всем пользователям. Ключи включают:
                - "checked": количество обработанных пользователей
                - "expired": количество истёкших подписок
                - "notified": количество отправленных уведомлений
                - "configs_deleted": количество удалённых VPN-конфигов

        """
        result: CheckAllSubscriptionsResponse | None = await self._run_check_all()

        stats = SubscriptionBotStats(
            checked=result.stats.checked if result else 0,
            expired=result.stats.expired if result else 0,
            notified=0,
            configs_deleted=0,
        )

        if not result:
            # Об ошибке уже сообщили админам внутри `_run_check_all` — здесь
            # не дублируем уведомление сводкой из нулей, которая выглядела бы
            # как «нормальный» день с checked=0, а не как сбой проверки.
            logger.debug(
                "check_all вернул None — пропускаю обработку событий и повторное уведомление"
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
            count_deleted = await self._trigger_config_deletion(
                event.user_id, event.configs, [AsyncSSHClientWG, AsyncSSHClientWG2]
            )
            stats.configs_deleted += count_deleted
            if count_deleted > 0:
                user_text = m_subscription_local.expire_subscription.delete_configs_user
                await self._send_user_message(
                    tg_id=event.user_id, message=user_text, event=event
                )

                admin_text = (
                    m_subscription_local.expire_subscription.admin_stats.format(
                        tg_id=event.user_id,
                        username=f"@{event.username}",
                        first_name=event.first_name,
                        last_name=event.last_name,
                        file_name="\n".join(cfg.file_name for cfg in event.configs),
                    )
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
