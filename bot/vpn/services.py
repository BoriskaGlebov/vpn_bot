import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from aiogram.types import User as TGUser
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import (
    AppError,
    SubscriptionNotFoundError,
    VPNConfigDeletionFailedError,
    VPNLimitError,
)
from bot.core.config import VPNNode, settings_bot
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser, SUserOut, SVPNConfigOut
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.utils.amnezia_exceptions import AmneziaError
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN, AsyncSSHClientVPN2
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG, AsyncSSHClientWG2
from bot.vpn.utils.mtproto import HostDockerSSHClient, MTProtoProxy
from bot.vpn.utils.x_ray_config import XRayRegistry
from bot.vpn.utils.x_ray_exceptions import ThreeXUIConfigNotFoundError, ThreeXUIError

ssh_lock = asyncio.Lock()
xray_lock = asyncio.Lock()

SSHClientFactory = Callable[
    ..., AsyncSSHClientVPN2 | AsyncSSHClientWG2 | AsyncSSHClientVPN | AsyncSSHClientWG
]


class VPNService:
    """Сервис управления VPN-конфигурациями и XRay-подписками.

    Отвечает за:
        - проверку лимитов пользователей
        - генерацию VPN/WireGuard-конфигураций
        - создание MTProto proxy-ссылок
        - управление XRay-подписками
        - сохранение конфигураций в БД

    Attributes
        api_adapter: Адаптер для работы с VPN API.
        user_adapter: Адаптер для работы с пользователями.
        xray_registry: Реестр XRay-адаптеров по локациям.

    """

    def __init__(
        self,
        adapter: VPNAPIAdapter,
        user_adapter: UsersAPIAdapter,
        xray_registry: XRayRegistry,
    ) -> None:
        """Инициализирует сервис управления VPN-конфигурациями.

        Args:
            adapter: Адаптер для взаимодействия с VPN API.
            user_adapter: Адаптер для работы с пользователями.
            xray_registry: Реестр XRay-адаптеров.

        """
        self.api_adapter = adapter
        self.user_adapter = user_adapter
        self.xray_registry = xray_registry

    async def _limit_and_user_inf(self, tg_user: TGUser) -> SUserOut:
        """Проверяет лимит пользователя и возвращает пользователя из БД.

        Args:
            tg_user (TGUser): Telegram-пользователь.

        Raises
            VPNLimitError: Если пользователь достиг лимита конфигураций.

        Returns
            SUserOut: Объект пользователя из БД.

        """
        logger.debug("Проверка лимитов пользователя tg_id={}", tg_user.id)

        limit = await self.api_adapter.check_limit(tg_id=tg_user.id)
        user, _ = await self.user_adapter.register(SUser(telegram_id=tg_user.id))

        if not limit.can_add:
            logger.warning(
                "Превышен лимит конфигов tg_id={} limit={}",
                user.telegram_id,
                limit.limit,
            )
            raise VPNLimitError(
                tg_id=user.telegram_id,
                limit=limit.limit,
                username=user.username or "",
            )

        logger.debug("Лимит ок tg_id={}", tg_user.id)
        return user

    async def generate_user_config(
        self,
        tg_user: TGUser,
        ssh_client_factory: SSHClientFactory,
        server_info: VPNNode,
    ) -> tuple[Path, Path, str]:
        """Генерирует VPN-конфигурацию пользователя через SSH и сохраняет её в БД.

        Алгоритм работы:
            1. Проверяет лимит конфигураций пользователя.
            2. Регистрирует пользователя в системе при необходимости.
            3. Подключается к VPN-серверу через SSH.
            4. Генерирует пользовательскую конфигурацию.
            5. Сохраняет метаданные конфигурации в БД.
            6. Выполняет rollback на стороне SSH при ошибке БД.

        Args:
            tg_user: Telegram-пользователь.
            ssh_client_factory:
                Фабрика SSH-клиентов для подключения к VPN-серверу.
            server_info:
                Конфигурация VPN-сервера.

        Returns
            tuple[Path,Path, str]:
                Кортеж:
                    - путь к конфигурационным файлам .conf .vpn
                    - публичный ключ или идентификатор конфигурации

        Raises
            VPNLimitError: Если пользователь превысил лимит конфигураций.
            APIClientError: При ошибке сохранения конфигурации в БД.
            AppError: При критической ошибке генерации конфигурации.

        """
        logger.info("Генерация VPN конфига tg_id={}", tg_user.id)

        user = await self._limit_and_user_inf(tg_user)

        async with ssh_lock:
            async with ssh_client_factory(
                host=server_info.host,
                username=server_info.username,
                known_hosts=None,
                container=server_info.container,
                use_local=server_info.use_local,
                location_prefix=server_info.location_prefix,
            ) as ssh:
                file_path1, file_path2, pub_key = await ssh.add_new_user_gen_config(
                    file_name=user.username
                )
                logger.info(
                    "Создал VPN конфиг file_name={} через {}",
                    file_path1.name,
                    ssh.__class__.__name__,
                )
                logger.info(
                    "Создал VPN конфиг file_name={} через {}",
                    file_path2.name,
                    ssh.__class__.__name__,
                )

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=f"{file_path1.name} / {file_path2.name}",
                pub_key=pub_key,
            )
            logger.info("Конфиг сохранён в БД tg_id={}", tg_user.id)

        except APIClientError as exc:
            logger.error(
                "Ошибка сохранения в БД, откат SSH tg_id={} error={}",
                tg_user.id,
                exc,
            )
            await ssh.full_delete_user(public_key=pub_key)
            raise

        return file_path1, file_path2, pub_key

    async def get_mtproto_url(
        self, ssh_client_factory: type[HostDockerSSHClient], server_info: VPNNode
    ) -> str:
        """Генерирует MTProto proxy-ссылку.

        Args:
            ssh_client_factory:
                SSH-клиент для подключения к docker-хосту.
            server_info:
                Конфигурация VPN-сервера.

        Returns
            str: MTProto proxy-ссылка.

        Raises
            AppError: Если MTProto proxy не настроен.

        """
        proxy_info = server_info.proxy
        if proxy_info is None:
            raise AppError(
                f"Прокси не настроен: {server_info.host} {server_info.location_prefix}"
            )
        async with ssh_lock:
            async with ssh_client_factory(
                host=f"{proxy_info.prefix}.{server_info.host}",
                username=server_info.username,
                use_local=server_info.use_local,
            ) as client:
                mtproto = MTProtoProxy(client=client, port=proxy_info.port)
                url_proxy = await mtproto.get_proxy_link()
                return url_proxy

    async def generate_xray_subscription(self, tg_user: TGUser, location: str) -> str:
        """Создаёт XRay-подписку и сохраняет её в БД.

        Алгоритм работы:
            1. Проверяет лимит пользователя.
            2. Определяет оставшееся время действия подписки.
            3. Создаёт XRay-конфигурации через адаптер локации.
            4. Сохраняет subscription-данные в БД.
            5. Выполняет rollback конфигураций при ошибке БД.

        Args:
            tg_user: Telegram-пользователь.
            location: Префикс локации для создания подключения.

        Returns
            str: URL XRay-подписки.

        Raises
            VPNLimitError: Если превышен лимит конфигураций.
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.
            APIClientError: При ошибке сохранения конфигурации в БД.
            RuntimeError: Если адаптер не вернул subscription ID.

        """
        logger.info("Генерация XRay tg_id={}", tg_user.id)

        user: SUserOut = await self._limit_and_user_inf(tg_user)

        sub = user.current_subscription
        if sub is None or not sub.is_active:
            # 0 дней 3x-ui трактует как "бессрочно" — нельзя допустить, чтобы
            # пользователь без активной подписки получил такой конфиг.
            raise SubscriptionNotFoundError(tg_id=tg_user.id)

        now = datetime.now(UTC)
        end = sub.end_date
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)

        days_left = max((end - now).days, 0) if end else 0

        logger.debug("Осталось дней tg_id={} days={}", tg_user.id, days_left)
        adapter = self.xray_registry.get(name=location)
        async with xray_lock:
            sub_info, sub_url = await adapter.add_new_config(
                tg_id=tg_user.id,
                days=days_left,
            )

        sub_ids = sub_info.get("sub_ids", [])
        config_ids = sub_info.get("config_ids", [])

        if not sub_ids:
            raise RuntimeError("sub_ids пуст")

        file_name = sub_ids[0]
        pub_key = json.dumps(config_ids)

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=file_name,
                pub_key=pub_key,
            )
        except APIClientError:
            logger.error("Ошибка XRay tg_id={} rollback", tg_user.id)

            async with xray_lock:
                for cid in config_ids:
                    await adapter.delete_config(config_id=cid)

            raise

        return sub_url

    @staticmethod
    def _collect_xray_config_ids(configs: list[SVPNConfigOut]) -> set[str]:
        """Собирает `config_id` всех XRay-конфигов пользователя.

        `pub_key` у XRay-конфигов — JSON-список `config_id` (по одному на
        каждый inbound, см. `ThreeXUIAdapter.add_new_config`); у WireGuard —
        сырой публичный ключ, который как JSON не парсится, поэтому такие
        конфиги просто пропускаются (WireGuard не хранит срок действия на
        сервере — продлевать там нечего).

        Args:
            configs: Список VPN-конфигов пользователя.

        Returns
            set[str]: Объединённое множество `config_id` по всем XRay-конфигам.

        """
        config_ids: set[str] = set()
        for config in configs:
            try:
                ids = json.loads(config.pub_key)
            except json.JSONDecodeError:
                continue
            if isinstance(ids, list):
                config_ids.update(ids)
        return config_ids

    async def extend_user_xray_subscription(self, user: SUserOut) -> list[str]:
        """Продлевает существующие XRay-конфигурации пользователя на всех нодах.

        Вызывается при продлении/активации платной подписки: сама подписка
        живёт в БД `api/`, но выданные ранее XRay-конфиги на панелях 3x-ui
        хранят свой собственный `expiryTime` и не продлеваются вместе с ней
        автоматически — без этого метода пользователь после оплаты продления
        всё равно терял бы доступ по старому сроку.

        Не создаёт новых конфигов (в отличие от `generate_xray_subscription`) —
        только обновляет `expiryTime` уже существующих, поэтому у
        пользователя без активной подписки или без XRay-конфигов — это no-op.

        Args:
            user: Пользователь с уже применённой (продлённой) подпиской —
                `current_subscription.end_date` используется как новая точка
                отсчёта оставшихся дней.

        Returns
            list[str]: `config_id` продлённых XRay-конфигураций. Пустой
                список, если у пользователя нет активной подписки или
                XRay-конфигов — это не ошибка.

        Raises
            ThreeXUIError: Если у пользователя есть XRay-конфиги, но продлить
                их не удалось ни на одной из зарегистрированных нод.

        """
        sub = user.current_subscription
        if sub is None or not sub.is_active:
            logger.debug(
                "Нет активной подписки — пропуск продления XRay tg_id={}",
                user.telegram_id,
            )
            return []

        now = datetime.now(UTC)
        end = sub.end_date
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
        days_left = max((end - now).days, 0) if end else 0

        if days_left <= 0:
            logger.debug(
                "Подписка истекает сегодня/бессрочная — пропуск продления XRay tg_id={}",
                user.telegram_id,
            )
            return []

        pending = self._collect_xray_config_ids(user.vpn_configs)
        if not pending:
            logger.debug(
                "У пользователя tg_id={} нет XRay-конфигов для продления",
                user.telegram_id,
            )
            return []

        logger.info(
            "Продление XRay-конфигов tg_id={} config_ids={} days={}",
            user.telegram_id,
            pending,
            days_left,
        )

        extended: list[str] = []
        last_error: ThreeXUIError | None = None

        async with xray_lock:
            for adapter in self.xray_registry.all():
                if not pending:
                    break
                try:
                    done = await adapter.extend_config(
                        config_ids=list(pending), days=days_left
                    )
                except ThreeXUIConfigNotFoundError:
                    continue
                except ThreeXUIError as exc:
                    logger.warning(
                        "Ошибка продления XRay-конфигов tg_id={} на {}: {}",
                        user.telegram_id,
                        adapter,
                        exc,
                    )
                    last_error = exc
                    continue
                extended.extend(done)
                pending.difference_update(done)

        if pending:
            logger.error(
                "Не удалось продлить часть XRay-конфигов tg_id={} config_ids={}",
                user.telegram_id,
                pending,
            )
            raise last_error or ThreeXUIConfigNotFoundError(config_ids=list(pending))

        logger.info(
            "XRay-конфиги продлены tg_id={} config_ids={}",
            user.telegram_id,
            extended,
        )
        return extended

    async def _delete_from_ssh_nodes(
        self, pub_key: str, file_name: str
    ) -> tuple[bool, bool]:
        """Пытается удалить конфиг WireGuard на всех Amnezia-нодах.

        Для каждой ноды пробует только те версии контейнера, которые для
        неё реально настроены в `settings_bot.vpn.nodes` (`container` —
        всегда, `container_old` — только если задан), а не обе версии
        вслепую по умолчанию классов. Раньше код всегда пробовал оба
        клиента (`AsyncSSHClientWG`/`AsyncSSHClientWG2`) с их именами
        контейнеров "по умолчанию" — из-за этого на нодах без старого
        контейнера (например, там, где `container_old` не задан) попытка
        гарантированно проваливалась ошибкой подключения к
        несуществующему контейнеру, и это ошибочно считалось реальным
        сбоем, блокируя сценарий "конфига уже нигде нет — можно чистить БД".

        Args:
            pub_key: Публичный ключ WireGuard-клиента.
            file_name: Имя файла — только для логирования.

        Returns
            tuple[bool, bool]: (найден_и_удалён, была_ошибка_соединения).

        """
        had_error = False
        for server_info in settings_bot.vpn.nodes.values():
            attempts: list[tuple[type[AsyncSSHClientWG], str]] = [
                (AsyncSSHClientWG2, server_info.container)
            ]
            if server_info.container_old:
                attempts.append((AsyncSSHClientWG, server_info.container_old))

            for client_cls, container in attempts:
                try:
                    async with client_cls(
                        host=server_info.host,
                        username=server_info.username,
                        container=container,
                        use_local=server_info.use_local,
                        location_prefix=server_info.location_prefix,
                    ) as ssh_client:
                        if await ssh_client.full_delete_user(public_key=pub_key):
                            logger.info(
                                "Конфиг {} удалён через {} ({}) на {}",
                                file_name,
                                client_cls.__name__,
                                container,
                                server_info.host,
                            )
                            return True, False
                except (AmneziaError, BrokenPipeError) as e:
                    logger.warning(
                        "Не удалось удалить {} через {} ({}) на {}: {}",
                        file_name,
                        client_cls.__name__,
                        container,
                        server_info.host,
                        e,
                    )
                    had_error = True
        return False, had_error

    async def _delete_from_xray(
        self, pub_key: str, file_name: str
    ) -> tuple[bool, bool]:
        """Пытается удалить конфиг XRay на всех зарегистрированных нодах 3x-ui.

        `pub_key` для XRay-конфигов — это JSON-список `config_id` (по одному
        на каждый inbound); если он не парсится как JSON, значит это не
        XRay-конфиг вовсе (WireGuard хранит там сырой публичный ключ).

        Args:
            pub_key: Публичный ключ (для XRay — JSON-список config_id).
            file_name: Имя файла — только для логирования.

        Returns
            tuple[bool, bool]: (найден_и_удалён, была_ошибка_запроса).

        """
        try:
            config_ids = json.loads(pub_key)
        except json.JSONDecodeError:
            return False, False

        deleted_any = False
        had_error = False
        for adapter in self.xray_registry.all():
            for config_id in config_ids:
                try:
                    if await adapter.delete_config(config_id=config_id):
                        deleted_any = True
                except APIClientError as e:
                    logger.warning(
                        "Ошибка удаления config_id={} в {}: {}",
                        config_id,
                        adapter,
                        e,
                    )
                    had_error = True
        if deleted_any:
            logger.info("Конфиг {} удалён через 3x-ui", file_name)
        return deleted_any, had_error

    async def delete_user_config(self, tg_id: int, config: SVPNConfigOut) -> bool:
        """Удаляет конфиг пользователя из внешнего сервиса и из БД.

        Пробует удалить конфиг сначала как WireGuard (Amnezia, по SSH, все
        ноды и обе версии контейнера), затем, если не найден — как XRay
        (3x-ui, по всем зарегистрированным нодам). Если конфиг не найден
        нигде, но и ошибок соединения не было — считаем его уже отсутствующим
        и всё равно удаляем запись из БД. Если были реальные ошибки — запись
        в БД не трогаем, чтобы не потерять её без фактического удаления.

        Args:
            tg_id: Telegram ID владельца конфига (для атрибуции в API).
            config: Конфиг для удаления.

        Returns
            bool: True, если конфиг был реально найден и удалён на внешнем
            сервисе; False, если он нигде не был найден (но запись в БД
            всё равно удалена).

        Raises
            VPNConfigDeletionFailedError: Если при удалении произошла ошибка
                соединения и небезопасно удалять запись из БД.

        """
        async with ssh_lock:
            deleted, had_error = await self._delete_from_ssh_nodes(
                config.pub_key, config.file_name
            )

        if not deleted:
            async with xray_lock:
                deleted, xray_error = await self._delete_from_xray(
                    config.pub_key, config.file_name
                )
                had_error = had_error or xray_error

        if not deleted and had_error:
            raise VPNConfigDeletionFailedError(file_name=config.file_name)

        if not deleted:
            logger.warning(
                "Конфиг {} не найден ни в Amnezia, ни в 3x-ui — удаляю только из БД",
                config.file_name,
            )

        await self.api_adapter.delete_config(
            file_name=config.file_name,
            pub_key=config.pub_key,
            tg_id=tg_id,
        )
        return deleted
