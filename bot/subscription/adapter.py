from dataclasses import dataclass
from typing import Any

from bot.integrations.api_client import APIClient
from bot.core.config import settings_bot
from shared.schemas.users import SUserOut


@dataclass
class SubscriptionCheck:
    premium: bool
    role: str
    is_active: bool


@dataclass
class TrialActivateResponse:
    status: str


class SubscriptionAdapter:
    def __init__(self, client: APIClient):
        self._client = client

    # ------------------------
    # CHECK PREMIUM
    # ------------------------
    async def check_premium(self, tg_id: int) -> SubscriptionCheck:
        data = await self._client.get(
            "/subscriptions/check/premium",
            params={"tg_id": tg_id},
        )

        return SubscriptionCheck(
            premium=data["premium"],
            role=data["role"],
            is_active=data["is_active"],
        )

    # ------------------------
    # ACTIVATE TRIAL
    # ------------------------
    async def activate_trial(self, tg_id: int, days: int=7) -> tuple[TrialActivateResponse,int]:
        data, status = await self._client.post(
            "/subscriptions/trial/activate",
            json={
                "tg_id": tg_id,
                "days": days,
            },
        )

        return TrialActivateResponse(status=data["status"]),status

    # ------------------------
    # ACTIVATE PAID
    # ------------------------
    async def activate_paid(
        self,
        tg_id: int,
        months: int,
        premium: bool,
    ) -> SUserOut:
        data, _ = await self._client.post(
            "/subscriptions/activate",
            json={
                "tg_id": tg_id,
                "months": months,
                "premium": premium,
            },
        )
        return SUserOut.model_validate(data)