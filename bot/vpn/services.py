import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from aiogram.types import User as TGUser
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import AppError, VPNLimitError
from bot.core.config import VPNNode
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser, SUserOut
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN, AsyncSSHClientVPN2
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG, AsyncSSHClientWG2
from bot.vpn.utils.mtproto import HostDockerSSHClient, MTProtoProxy
from bot.vpn.utils.x_ray_config import XRayRegistry

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
                user_id=user.telegram_id,
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
            APIClientError: При ошибке сохранения конфигурации в БД.
            RuntimeError: Если адаптер не вернул subscription ID.

        """
        logger.info("Генерация XRay tg_id={}", tg_user.id)

        user: SUserOut = await self._limit_and_user_inf(tg_user)

        sub = user.current_subscription
        now = datetime.now(UTC)

        end = sub.end_date if sub else None
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
