from bot.integrations.api_client import APIClient
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateResponse,
)


class VPNAPIAdapter:
    """Адаптер для работы с VPN API."""

    def __init__(self, client: APIClient) -> None:
        self.client = client

    async def check_limit(self, tg_id: int) -> SVPNCheckLimitResponse:
        """Проверяет лимит конфигов."""
        data = await self.client.get(
            "/api/vpn/limit",
            params={"tg_id": tg_id},
        )

        return SVPNCheckLimitResponse(**data)

    async def add_config(
        self,
        tg_id: int,
        file_name: str,
        pub_key: str,
    ) -> SVPNCreateResponse:
        """Сохраняет конфиг."""
        data, _ = await self.client.post(
            "/api/vpn/config",
            json={
                "tg_id": tg_id,
                "file_name": file_name,
                "pub_key": pub_key,
            },
        )

        return SVPNCreateResponse(**data)
