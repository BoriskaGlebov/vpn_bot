from bot.integrations.api_client import APIClient
from shared.schemas.referral import (
    GrantReferralBonusRequest,
    GrantReferralBonusResponse,
    RegisterReferralRequest,
    RegisterReferralResponse,
)


class ReferralAdapter:
    """Клиент для работы с referrals API."""

    def __init__(self, client: APIClient) -> None:
        self.client = client

    async def register_referral(
        self,
        payload: RegisterReferralRequest,
    ) -> RegisterReferralResponse:
        """Регистрация реферала."""
        data, _ = await self.client.post(
            "/api/referrals/register",
            json=payload.model_dump(),
        )

        return RegisterReferralResponse.model_validate(data)

    async def grant_bonus(
        self,
        payload: GrantReferralBonusRequest,
    ) -> GrantReferralBonusResponse:
        """Начисление бонуса рефералу."""
        data, _ = await self.client.post(
            "/api/referrals/bonus",
            json=payload.model_dump(),
        )

        return GrantReferralBonusResponse.model_validate(data)
