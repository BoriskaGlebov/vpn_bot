from pathlib import Path

from aiogram.types import User as TGUser
from sqlalchemy.ext.asyncio import AsyncSession

from bot.subscription.models import DEVICE_LIMITS
from bot.users.dao import UserDAO
from bot.users.models import User
from bot.users.schemas import SUserTelegramID
from bot.vpn.dao import VPNConfigDAO
from bot.vpn.utils.amnezia_vpn import AsyncSSHClientVPN
from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


class VPNService:
    """Сервис для работы с VPN-конфигами и подписками пользователей."""

    async def generate_user_config(
        self,
        session: AsyncSession,
        user: TGUser,
        ssh_client: AsyncSSHClientWG | AsyncSSHClientVPN,
    ) -> tuple[Path, str]:
        """Генерирует новый VPN-конфиг и сохраняет его в базе данных.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (TGUser): Telegram-пользователь.
            ssh_client (AsyncSSHClientWG | AsyncSSHClientVPN): SSH-клиент для генерации конфига.

        Raises
            ValueError: Если пользователь не найден или достигнут лимит конфигов.

        Returns
            tuple[Path, str]: Путь к файлу конфига и публичный ключ.

        """
        schema_user = SUserTelegramID(telegram_id=user.id)
        user_model = await UserDAO.find_one_or_none(
            session=session, filters=schema_user
        )
        if user_model is None:
            raise ValueError("Нет пользвоателя в БД")

        can_add = await VPNConfigDAO.can_add_config(
            session=session, user_id=user_model.id
        )
        if not can_add:
            raise ValueError(
                f"Достигнут лимит конфигов (максимум {DEVICE_LIMITS.get(user_model.subscription.type, 0)})."
            )

        file_path, pub_key = await ssh_client.add_new_user_gen_config(
            file_name=user_model.username
        )

        await VPNConfigDAO.add_config(
            session=session,
            user_id=user_model.id,
            file_name=file_path.name,
            pub_key=pub_key,
        )

        return file_path, pub_key

    @staticmethod
    async def get_subscription_info(tg_id: int, session: AsyncSession) -> str:
        """Возвращает информацию о подписке пользователя и его VPN-конфигах.

        Args:
            tg_id (int): ID Telegram-пользователя.
            session (AsyncSession): Асинхронная сессия SQLAlchemy.

        Raises
            ValueError: Если пользователь не найден.

        Returns
            str: Текст с информацией о подписке и списком конфигов.

        """
        user: User | None = await UserDAO.find_one_or_none(
            session=session, filters=SUserTelegramID(telegram_id=tg_id)
        )
        if not user:
            raise ValueError(f"Пользователь с id={tg_id} не найден")

        subscription = user.subscription
        if not subscription:
            return "У вас нет подписки."

        status = "✅ Активна" if subscription.is_active else "🔒 Неактивна"
        sbs_type = (
            f"<b>{subscription.type.value.upper()}</b>"
            if subscription.type is not None
            else ""
        )
        remaining_days = subscription.remaining_days()
        if remaining_days is None:
            remaining_text = "бессрочная"
        else:
            remaining_text = f"{remaining_days} дней осталось"
        conf_list = "\n".join([conf.file_name for conf in user.vpn_configs])
        return f"{status} {sbs_type} — {remaining_text} - {subscription}\n{conf_list}"
