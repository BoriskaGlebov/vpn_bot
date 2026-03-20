from api.users.models import User
from api.users.schemas import (
    SRoleOut,
    SSubscriptionOut,
    SUserOut,
    SVPNConfigOut,
)


class UserMapper:
    """Преобразование ORM моделей User в Pydantic схемы."""

    @staticmethod
    async def to_schema(user: User) -> SUserOut:
        """Конвертирует User ORM → SUserOut DTO."""
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
