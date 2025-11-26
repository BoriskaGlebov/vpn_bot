import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from loguru._logger import Logger
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import connection
from bot.utils.base_router import BaseRouter
from bot.vpn.services import VPNService

if TYPE_CHECKING:
    pass

ssh_lock = asyncio.Lock()


class VPNRouter(BaseRouter):
    """Роутер для обработки команд VPN."""

    key_path = Path().home() / ".ssh" / "test_vpn"

    def __init__(self, bot: Bot, logger: Logger, vpn_service: VPNService) -> None:
        super().__init__(bot, logger)
        self.vpn_service = vpn_service

    def _register_handlers(self) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def get_config_amnezia_vpn(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def get_config_amnezia_wg(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        pass

    @BaseRouter.log_method
    @connection()
    async def check_subscription(
        self, message: Message, session: AsyncSession, state: FSMContext
    ) -> None:
        pass
