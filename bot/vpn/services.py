import json
from datetime import UTC, datetime
from pathlib import Path

from aiogram.types import User as TGUser
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import VPNLimitError
from bot.core.config import settings_bot
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser, SUserOut
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG
from bot.vpn.utils.x_ray_config import ThreeXUIAdapter


# TODO тесты логи документация
class VPNService:
    """Сервис управления VPN-конфигурациями и XRay-подписками."""

    def __init__(
        self,
        adapter: VPNAPIAdapter,
        user_adapter: UsersAPIAdapter,
        xray_adapter: ThreeXUIAdapter,
    ) -> None:
        self.api_adapter = adapter
        self.user_adapter = user_adapter
        self.xray_adapter = xray_adapter

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
        ssh_client: AsyncSSHClientWG | AsyncSSHClientVPN,
    ) -> tuple[Path, str]:
        """Создаёт VPN-конфиг через SSH и сохраняет его в БД.

        Args:
            tg_user (TGUser): Telegram-пользователь.
            ssh_client (AsyncSSHClientWG | AsyncSSHClientVPN): SSH-клиент.

        Raises
            VPNLimitError: Если достигнут лимит.
            APIClientError: Если ошибка при сохранении в БД.

        Returns
            tuple[Path, str]:
                - Path: путь к конфигу
                - str: публичный ключ

        """
        logger.info("Генерация VPN конфига tg_id={}", tg_user.id)

        user = await self._limit_and_user_inf(tg_user)

        file_path, pub_key = await ssh_client.add_new_user_gen_config(
            file_name=user.username
        )

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=file_path.name,
                pub_key=pub_key,
            )
            logger.info("Конфиг сохранён в БД tg_id={}", tg_user.id)

        except APIClientError as exc:
            logger.error(
                "Ошибка сохранения в БД, откат SSH tg_id={} error={}",
                tg_user.id,
                exc,
            )
            await ssh_client.full_delete_user(public_key=pub_key)
            raise

        return file_path, pub_key

    async def generate_xray_subscription(
        self,
        tg_user: TGUser,
    ) -> str:
        """Создаёт XRay-подписку и сохраняет её в БД.

        Args:
            tg_user (TGUser): Telegram-пользователь.

        Raises
            VPNLimitError: Если превышен лимит конфигураций.
            APIClientError: Если ошибка при сохранении в БД.

        Returns
            str: URL подписки.

        """
        logger.info("Генерация XRay подписки tg_id={}", tg_user.id)

        user: SUserOut = await self._limit_and_user_inf(tg_user)
        cur_sub = user.current_subscription
        dt = cur_sub.end_date if cur_sub else None
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        delta_days: int = max((dt - now).days, 0) if dt else 0

        logger.debug("Срок подписки (дни) tg_id={} days={}", tg_user.id, delta_days)

        sub_inf, sub_url = await self.xray_adapter.add_new_config(
            tg_id=tg_user.id,
            days=delta_days,
            inbounds=settings_bot.inbounds,
        )

        sub_ids: list[str] = sub_inf.get("sub_ids", [])
        config_ids: list[str] = sub_inf.get("config_ids", [])

        if not sub_ids:
            logger.error("Не получены sub_ids tg_id={}", tg_user.id)
            raise RuntimeError("sub_ids пуст")

        file_name: str = sub_ids[0]

        pub_key: str = json.dumps(config_ids)

        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=file_name,
                pub_key=pub_key,
            )
            logger.info("Подписка сохранена в БД tg_id={}", tg_user.id)

        except APIClientError as exc:
            logger.error(
                "Ошибка сохранения подписки, откат XRay tg_id={} error={}",
                tg_user.id,
                exc,
            )

            for config_id in config_ids:
                await self.xray_adapter.delete_config(
                    config_id=config_id,
                    inbounds=settings_bot.inbounds,
                )

            raise

        return sub_url
