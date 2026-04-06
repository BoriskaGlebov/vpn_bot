from pathlib import Path

from aiogram.types import User as TGUser
from loguru import logger

from bot.app_error.api_error import APIClientError
from bot.app_error.base_error import VPNLimitError
from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUser
from bot.vpn.adapter import VPNAPIAdapter
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


class VPNService:
    """Сервис для работы с VPN-конфигами и подписками пользователей."""

    def __init__(self, adapter: VPNAPIAdapter, user_adapter: UsersAPIAdapter) -> None:
        self.api_adapter = adapter
        self.user_adapter = user_adapter

    async def generate_user_config(
        self,
        tg_user: TGUser,
        ssh_client: AsyncSSHClientWG | AsyncSSHClientVPN,
    ) -> tuple[Path, str]:
        """Генерирует новый VPN-конфиг и сохраняет его в базе данных.

        Args:
            tg_user (TGUser): Telegram-пользователь.
            ssh_client (AsyncSSHClientWG | AsyncSSHClientVPN): SSH-клиент для генерации конфига.

        Raises
            UserNotFoundError: Если пользователь не найден.
            VPNLimitError: Достигнут лимит конфигов.

        Returns
            tuple[Path, str]: Путь к файлу конфига и публичный ключ.

        """
        limit = await self.api_adapter.check_limit(tg_id=tg_user.id)
        user, _ = await self.user_adapter.register(SUser(telegram_id=tg_user.id))

        if not limit.can_add:
            raise VPNLimitError(
                user_id=user.telegram_id,
                limit=limit.limit,
                username=user.username or "",
            )

        file_path, pub_key = await ssh_client.add_new_user_gen_config(
            file_name=user.username
        )
        try:
            await self.api_adapter.add_config(
                tg_id=user.telegram_id,
                file_name=file_path.name,
                pub_key=pub_key,
            )
        except APIClientError as exc:
            logger.error(str(exc))
            await ssh_client.full_delete_user(public_key=pub_key)
            raise
        return file_path, pub_key
