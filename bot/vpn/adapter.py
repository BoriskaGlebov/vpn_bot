from bot.core.config import settings_bot
from bot.integrations.api_client import APIClient
from bot.vpn.schemas import (
    SVPNCheckLimitResponse,
    SVPNCreateRequest,
    SVPNCreateResponse,
    SVPNDeleteRequest,
    SVPNDeleteResponse,
)


# TODO ТЕстирование нужно
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

        return SVPNCheckLimitResponse.model_validate(data)

    async def add_config(
        self,
        tg_id: int,
        file_name: str,
        pub_key: str,
    ) -> SVPNCreateResponse:
        """Сохраняет конфиг."""
        data, _ = await self.client.post(
            "/api/vpn/config",
            json=SVPNCreateRequest(
                tg_id=tg_id, file_name=file_name, pub_key=pub_key
            ).model_dump(),
        )

        return SVPNCreateResponse.model_validate(data)

    async def delete_config(self, file_name: str, pub_key: str) -> SVPNDeleteResponse:
        """Удаление конфиг файла из БД API.

        Args:
            file_name: Название файла
            pub_key: Публичный ключ

        Returns
            SVPNDeleteResponse: количество удаленных файлов.

        """
        admin_id = next(iter(settings_bot.admin_ids), None)

        data, _ = await self.client.delete(
            "/api/vpn/config",
            json=SVPNDeleteRequest(file_name=file_name, pub_key=pub_key).model_dump(),
            headers={"X-Telegram-Id": str(admin_id)},
        )
        return SVPNDeleteResponse.model_validate(data)
