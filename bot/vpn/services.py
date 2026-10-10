import asyncio
import json
from collections.abc import Callable, Iterable
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
from bot.vpn.utils.amnezia_wg import (
    AsyncSSHClientWG,
    AsyncSSHClientWG2,
    AsyncSSHClientWG3,
)
from bot.vpn.utils.mtproto import HostDockerSSHClient, MTProtoProxy
from bot.vpn.utils.x_ray_config import XRayRegistry
from bot.vpn.utils.x_ray_exceptions import ThreeXUIConfigNotFoundError, ThreeXUIError
from shared.enums.vpn_enum import VPNBackend, VPNProtocol

ssh_lock = asyncio.Lock()
xray_lock = asyncio.Lock()

SSHClientFactory = Callable[
    ...,
    AsyncSSHClientVPN2
    | AsyncSSHClientWG2
    | AsyncSSHClientWG3
    | AsyncSSHClientVPN
    | AsyncSSHClientWG,
]

_WG_CLIENT_BY_PROTOCOL_VERSION: dict[str, type[AsyncSSHClientWG]] = {
    "v1": AsyncSSHClientWG,
    "v2": AsyncSSHClientWG2,
    "v3": AsyncSSHClientWG3,
}


def ssh_client_factory_for(node: VPNNode) -> type[AsyncSSHClientWG]:
    """Выбирает класс SSH-клиента для генерации AmneziaWG-конфига под ноду.

    Args:
        node (VPNNode): Конфигурация ноды с полем `protocol_version`.

    Returns
        type[AsyncSSHClientWG]: `AsyncSSHClientWG`/`WG2`/`WG3` — тот, что
            умеет генерировать конфиг для протокола этой ноды.

    """
    return _WG_CLIENT_BY_PROTOCOL_VERSION[node.protocol_version]


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
        node_name: str,
    ) -> tuple[Path, Path, Path, str]:
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
            node_name:
                Имя ноды (ключ в settings_bot.vpn.nodes) — сохраняется в
                VPNConfig.node_name, чтобы scheduler мог обращаться сразу
                к нужному серверу без перебора всех локаций.

        Returns
            tuple[Path, Path, Path, str]:
                Кортеж:
                    - путь к конфигурационным файлам .conf, .vpn, QR-код
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
                (
                    file_path1,
                    file_path2,
                    file_path3,
                    pub_key,
                ) = await ssh.add_new_user_gen_config(file_name=user.username)
                for file_path in (file_path1, file_path2, file_path3):
                    logger.info(
                        "Создал VPN конфиг file_name={} через {}",
                        file_path.name,
                        ssh.__class__.__name__,
                    )

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=f"{file_path1.name} / {file_path2.name} / {file_path3.name}",
                pub_key=pub_key,
                node_name=node_name,
                backend=VPNBackend.AMNEZIA,
                protocol=VPNProtocol.for_wg(server_info.protocol_version),
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

        return file_path1, file_path2, file_path3, pub_key

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
        protocols = sub_info.get("protocols", [])

        if not sub_ids:
            raise RuntimeError("sub_ids пуст")

        file_name = sub_ids[0]
        pub_key = json.dumps(config_ids)

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=file_name,
                pub_key=pub_key,
                node_name=location,
                backend=VPNBackend.XRAY,
                protocol=",".join(protocols),
                config_ids=config_ids,
            )
        except APIClientError:
            logger.error("Ошибка XRay tg_id={} rollback", tg_user.id)

            async with xray_lock:
                for cid in config_ids:
                    await adapter.delete_config(config_id=cid)

            raise

        return sub_url

    @staticmethod
    def _group_xray_config_ids(
        configs: list[SVPNConfigOut],
    ) -> tuple[dict[str, set[str]], set[str]]:
        """Группирует `config_id` XRay-конфигов пользователя по ноде.

        Конфиги, у которых `node_name` уже известен (заполняется при создании,
        см. `generate_xray_subscription`), группируются по ноде — можно
        обратиться сразу к нужному адаптеру вместо перебора всех
        зарегистрированных нод. Конфиги старого формата (созданы до появления
        `node_name`/`config_ids`) возвращаются отдельным множеством — по ним
        по-прежнему приходится перебирать все ноды (см. `xray_registry.all()`
        в вызывающем коде).

        `config_ids` берётся из одноимённого поля, если оно заполнено; иначе
        (старые записи) — из `pub_key`, который для XRay-конфигов является
        JSON-списком `config_id` (см. `ThreeXUIAdapter.add_new_config`). У
        WireGuard-конфигов `pub_key` — сырой публичный ключ, который как JSON
        не парсится, поэтому такие конфиги просто пропускаются (WireGuard не
        хранит срок действия на сервере — продлевать там нечего).

        Args:
            configs: Список VPN-конфигов пользователя.

        Returns
            tuple[dict[str, set[str]], set[str]]:
                (config_id по нодам, config_id без известной ноды).

        """
        by_node: dict[str, set[str]] = {}
        legacy: set[str] = set()
        for config in configs:
            if config.backend and config.backend != VPNBackend.XRAY:
                continue
            ids = config.config_ids
            if ids is None:
                try:
                    parsed = json.loads(config.pub_key)
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed, list):
                    continue
                ids = parsed
            if config.node_name:
                by_node.setdefault(config.node_name, set()).update(ids)
            else:
                legacy.update(ids)
        return by_node, legacy

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

        by_node, legacy = self._group_xray_config_ids(user.vpn_configs)
        if not by_node and not legacy:
            logger.debug(
                "У пользователя tg_id={} нет XRay-конфигов для продления",
                user.telegram_id,
            )
            return []

        logger.info(
            "Продление XRay-конфигов tg_id={} by_node={} legacy={} days={}",
            user.telegram_id,
            by_node,
            legacy,
            days_left,
        )

        extended: list[str] = []
        pending: set[str] = set()
        last_error: ThreeXUIError | None = None

        async with xray_lock:
            # Конфиги с известной нодой — обращаемся сразу к нужному адаптеру,
            # без перебора всех зарегистрированных нод.
            for node_name, ids in by_node.items():
                adapter = self.xray_registry.get_optional(node_name)
                if adapter is None:
                    # Нода была удалена из конфигурации после создания
                    # конфига — деградируем до перебора наравне с legacy.
                    legacy.update(ids)
                    continue
                try:
                    done = await adapter.extend_config(
                        config_ids=list(ids), days=days_left
                    )
                except ThreeXUIConfigNotFoundError:
                    pending.update(ids)
                    continue
                except ThreeXUIError as exc:
                    logger.warning(
                        "Ошибка продления XRay-конфигов tg_id={} на {}: {}",
                        user.telegram_id,
                        adapter,
                        exc,
                    )
                    last_error = exc
                    pending.update(set(ids) - set(done))
                    continue
                extended.extend(done)
                pending.update(set(ids) - set(done))

            # Конфиги без известной ноды (созданы до появления node_name) —
            # старое поведение: перебор всех нод до первого совпадения.
            for adapter in self.xray_registry.all() if legacy else []:
                if not legacy:
                    break
                try:
                    done = await adapter.extend_config(
                        config_ids=list(legacy), days=days_left
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
                legacy.difference_update(done)
            pending.update(legacy)

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
        self, pub_key: str, file_name: str, node_name: str | None = None
    ) -> tuple[bool, bool]:
        """Пытается удалить конфиг WireGuard на Amnezia-нодах.

        Если `node_name` известен (заполняется при создании конфига, см.
        `generate_user_config`) и такая нода реально сконфигурирована —
        пробует удалить только на ней, без обращения к остальным. Если
        `node_name` не передан или ноды с таким именем больше нет — старое
        поведение: перебор всех нод (нужно для записей, созданных до
        появления `node_name`, либо если нода была переименована/удалена).

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
            node_name: Имя ноды, на которой создан конфиг, если известно.

        Returns
            tuple[bool, bool]: (найден_и_удалён, была_ошибка_соединения).

        """
        nodes: Iterable[VPNNode] = settings_bot.vpn.nodes.values()
        if node_name is not None:
            known_node = settings_bot.vpn.nodes.get(node_name)
            if known_node is not None:
                nodes = [known_node]

        had_error = False
        for server_info in nodes:
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
        self,
        pub_key: str,
        file_name: str,
        node_name: str | None = None,
        config_ids: list[str] | None = None,
    ) -> tuple[bool, bool]:
        """Пытается удалить конфиг XRay на панелях 3x-ui.

        Если `node_name` известен и адаптер для такой ноды зарегистрирован —
        удаляет только на ней. Иначе (старая запись без `node_name`, либо
        нода с тех пор пропала из реестра) — перебирает все зарегистрированные
        ноды, как раньше.

        `config_ids`, если передан, используется напрямую; иначе (старые
        записи) парсится из `pub_key` — для XRay-конфигов это JSON-список
        `config_id` (по одному на каждый inbound). Если он не парсится как
        JSON, значит это не XRay-конфиг вовсе (WireGuard хранит там сырой
        публичный ключ).

        Args:
            pub_key: Публичный ключ (для XRay — JSON-список config_id).
            file_name: Имя файла — только для логирования.
            node_name: Имя ноды, на которой создан конфиг, если известно.
            config_ids: Список config_id, если известен заранее.

        Returns
            tuple[bool, bool]: (найден_и_удалён, была_ошибка_запроса).

        """
        if config_ids is None:
            try:
                config_ids = json.loads(pub_key)
            except json.JSONDecodeError:
                return False, False

        adapters = self.xray_registry.all()
        known_adapter = self.xray_registry.get_optional(node_name)
        if known_adapter is not None:
            adapters = [known_adapter]

        deleted_any = False
        had_error = False
        for adapter in adapters:
            for config_id in config_ids:
                try:
                    if await adapter.delete_config(config_id=config_id):
                        deleted_any = True
                except (APIClientError, ThreeXUIError) as e:
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

        Если `config.backend` известен (заполняется при создании, см.
        `generate_user_config`/`generate_xray_subscription`) — пробует
        удалить только на соответствующем бэкенде, без обращения ко второму.
        Для старых записей без `backend` — как раньше: сначала WireGuard
        (Amnezia, по SSH), затем, если не найден — XRay (3x-ui). В обоих
        случаях `config.node_name` (если известен) используется для прямого
        обращения к нужной ноде вместо перебора всех зарегистрированных.

        Если конфиг не найден нигде, но и ошибок соединения не было —
        считаем его уже отсутствующим и всё равно удаляем запись из БД. Если
        были реальные ошибки — запись в БД не трогаем, чтобы не потерять её
        без фактического удаления.

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
        deleted = False
        had_error = False

        if config.backend != VPNBackend.XRAY:
            async with ssh_lock:
                deleted, had_error = await self._delete_from_ssh_nodes(
                    config.pub_key, config.file_name, node_name=config.node_name
                )

        if not deleted and config.backend != VPNBackend.AMNEZIA:
            async with xray_lock:
                deleted, xray_error = await self._delete_from_xray(
                    config.pub_key,
                    config.file_name,
                    node_name=config.node_name,
                    config_ids=config.config_ids,
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
