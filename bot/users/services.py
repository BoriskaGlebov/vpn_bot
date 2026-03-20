from aiogram.types import User as TgUser
from loguru import logger

from bot.users.adapter import UsersAPIAdapter
from bot.users.models import User
from shared.schemas.users import (
    SRoleOut,
    SSubscriptionOut,
    SUser,
    SUserOut,
    SVPNConfigOut,
)


class UserService:
    """Сервис для управления пользователями.

    Отвечает за:
        - регистрацию пользователя;
        - получение и преобразование данных пользователя;
        - подготовку схем (DTO) для внешнего использования.
    """

    def __init__(self, adapter: UsersAPIAdapter) -> None:
        """Инициализирует сервис пользователей.

        Args:
            adapter: Адаптер для взаимодействия с Users API.

        """
        self.api_adapter = adapter

    # TODO Надо это убрать мне кажется оно в конце концев не будет нужно.
    @staticmethod
    async def get_user_schema(user: User) -> SUserOut:
        """Преобразует модель пользователя в Pydantic-схему.

        Использует `model_construct` для быстрого создания схем без валидации.

        Args:
            user: Доменная модель пользователя.

        Returns
            SUserOut: Pydantic-схема пользователя.

        """
        logger.debug("Начало преобразования User -> SUserOut (user_id={})", user.id)
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
        logger.debug(
            "Успешно преобразован user_id={} (subs={}, vpn_configs={})",
            user.id,
            len(user.subscriptions),
            len(user.vpn_configs),
        )

        return user_schema

    async def register_or_get_user(
        self, telegram_user: TgUser
    ) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя или возвращает существующего.

        Args:
            telegram_user: Объект пользователя Telegram.

        Returns
            Кортеж:
                - SUserOut: данные пользователя;
                - bool: флаг, указывающий, был ли пользователь создан.

        """
        logger.info(
            "Регистрация/получение пользователя telegram_id={}",
            telegram_user.id,
        )
        schema_user = SUser(
            telegram_id=telegram_user.id,
            username=telegram_user.username or f"Гость_{telegram_user.id}",
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
        )

        user, is_new = await self.api_adapter.register(schema_user)
        if is_new:
            logger.success(
                "Создан новый пользователь telegram_id={} user_id={}",
                telegram_user.id,
                user.id,
            )
        else:
            logger.debug(
                "Получен существующий пользователь telegram_id={} user_id={}",
                telegram_user.id,
                user.id,
            )

        return user, is_new
