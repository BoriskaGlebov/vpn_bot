from bot.integrations.api_client import APIClient
from shared.schemas.users import SUser, SUserOut


class UsersAPIAdapter:
    """Клиент для работы с users API."""

    def __init__(self, client: APIClient) -> None:
        self.client = client

    async def register(self, user: SUser) -> tuple[SUserOut, bool]:
        """Регистрация или получение пользователя."""
        data, status_code = await self.client.post(
            "/api/users/register",
            json=user.model_dump(),
        )
        is_new = True
        if status_code == 200:
            is_new = False

        return SUserOut.model_validate(data), is_new
