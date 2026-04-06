from api.users.models import User
from api.users.schemas import (
    SRoleOut,
    SSubscriptionOut,
    SUserOut,
    SUserWithReferralStats,
    SVPNConfigOut,
)


class UserMapper:
    """Mapper для преобразования ORM-модели User в Pydantic DTO-схемы.

    Примечание:
        Используется `model_construct`, так как предполагается,
        что входные данные уже валидны (из ORM).
        Это позволяет избежать лишней валидации и ускорить преобразование.
    """

    @staticmethod
    async def to_schema(user: User) -> SUserOut:
        """Преобразует ORM-объект User в DTO-схему SUserOut.

        Args:
            user (User): ORM-модель пользователя с предзагруженными связями:
                - role
                - subscriptions
                - vpn_configs
                - current_subscription (optional)

        Returns
            SUserOut: DTO-представление пользователя.

        """
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

    @staticmethod
    async def to_schema_with_referrals(user: User) -> SUserWithReferralStats:
        """Преобразует User в расширенную DTO-схему с реферальной статистикой.

        Дополнительно рассчитывает: количество приглашённых пользователей,
        количество пользователей с выданным бонусом, конверсию (paid / total)

        Args:
            user (User): ORM-модель пользователя с загруженной связью invited_users.

        Returns
            SUserWithReferralStats: DTO с дополнительной реферальной статистикой.

        """
        base_schema: SUserOut = await UserMapper.to_schema(user)

        invited_users = getattr(user, "invited_users", [])

        referrals_count: int = len(invited_users)

        paid_referrals_count: int = sum(1 for ref in invited_users if ref.bonus_given)

        referral_conversion: float = (
            paid_referrals_count / referrals_count if referrals_count else 0.0
        )

        return SUserWithReferralStats.model_construct(
            **base_schema.model_dump(
                exclude_none=True,
                exclude={
                    "role",
                    "subscriptions",
                    "vpn_configs",
                    "current_subscription",
                },
            ),
            role=base_schema.role,
            subscriptions=base_schema.subscriptions,
            vpn_configs=base_schema.vpn_configs,
            current_subscription=base_schema.current_subscription,
            referrals_count=referrals_count,
            paid_referrals_count=paid_referrals_count,
            referral_conversion=referral_conversion,
        )
