from core.config import settings_api
from sqlalchemy.ext.asyncio import AsyncSession

from api.users.dao import UserDAO
from api.users.models import User
from api.users.schemas import (
    SRole,
    SRoleOut,
    SSubscriptionOut,
    SUser,
    SUserOut,
    SUserTelegramID,
    SVPNConfigOut,
)


class UserService:
    """Сервис для управления пользователями.

    Отвечает за регистрацию и получение данных пользователя.
    """

    @staticmethod
    async def get_user_schema(user: User) -> SUserOut:
        """Получаю из пользователя корректную Pydentic схему быстро."""
        user_schema = SUserOut.model_construct(**user.__dict__)
        schema_role = SRoleOut.model_construct(**user.role.__dict__)
        schema_subscription = [
            SSubscriptionOut.model_construct(**subscr.__dict__)
            for subscr in user.subscriptions
        ]
        schema_configs = [
            SVPNConfigOut.model_construct(**config.__dict__)
            for config in user.vpn_configs
        ]

        user_schema.role = schema_role
        user_schema.subscriptions = schema_subscription
        user_schema.vpn_configs = schema_configs
        user_schema.current_subscription = (
            SSubscriptionOut.model_construct(**user.current_subscription.__dict__)
            if user.current_subscription
            else None
        )
        return user_schema

    async def register_or_get_user(
        self, session: AsyncSession, telegram_user: SUser
    ) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя, если он отсутствует, или возвращает существующего.

        Если пользователь с данным Telegram ID отсутствует в базе данных, создаётся новая
        запись, а также автоматически назначается роль:
        - "admin" — если Telegram ID находится в списке `settings_bot.ADMIN_IDS`
        - "user" — для всех остальных пользователей

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy для работы с БД.
            telegram_user (SUser): Схема с данными из телеграм пользователя.

        Returns
            tuple[SUserOut, bool]: Кортеж из:
                - экземпляра схемы `SUserOut`
                - булевого флага:
                    - `True`, если пользователь был создан;
                    - `False`, если пользователь уже существовал.

        """
        user = await UserDAO.find_one_or_none(
            session=session,
            filters=SUserTelegramID(telegram_id=telegram_user.telegram_id),
        )
        if not user:
            schema_user = SUser(
                telegram_id=telegram_user.telegram_id,
                username=telegram_user.username or f"Гость_{telegram_user.telegram_id}",
                first_name=telegram_user.first_name,
                last_name=telegram_user.last_name,
            )
            schema_role = SRole(
                name=(
                    "admin"
                    if telegram_user.telegram_id in settings_api.admin_ids
                    else "user"
                )
            )
            user = await UserDAO.add_role_subscription(
                session=session,
                values_user=schema_user,
                values_role=schema_role,
            )
            return await UserService.get_user_schema(user), True
        return await UserService.get_user_schema(user), False
