from bot.integrations.api_client import APIClient
from bot.users.schemas import SUser, SUserOut, SUserWithReferralStats


class UsersAPIAdapter:
    """Адаптер для взаимодействия с Users API.

    Инкапсулирует HTTP-вызовы и преобразует ответы API
    в Pydantic-схемы.

    """

    def __init__(self, client: APIClient) -> None:
        """Инициализация адаптера.

        Args:
            client (APIClient): HTTP-клиент для выполнения запросов к API.

        """
        self.client = client

    async def register(self, user: SUser) -> tuple[SUserOut, bool]:
        """Регистрирует пользователя или возвращает существующего.

        Выполняет POST-запрос к `/api/users/register`.

        Args:
            user (SUser): Входная схема пользователя.

        Returns
            Tuple[SUserOut, bool]:
                - SUserOut: DTO пользователя из ответа API.
                - bool: Флаг, указывающий, был ли пользователь создан:
                    - True — новый пользователь
                    - False — пользователь уже существовал

        Raises
            APIClientError: Если ответ API не соответствует ожидаемой структуре.

        """
        data, status_code = await self.client.post(
            "/api/users/register",
            json=user.model_dump(),
        )
        is_new = True
        if status_code == 200:
            is_new = False

        return SUserOut.model_validate(data), is_new

    async def get_referrals(self, telegram_id: int) -> SUserWithReferralStats:
        """Получает пользователя с реферальной статистикой.

        Выполняет GET-запрос к `/api/users/{telegram_id}/referrals`.

        Args:
            telegram_id (int): Telegram ID пользователя.

        Returns
            SUserWithReferralStats: DTO пользователя, включающий:
                - referrals_count (int): Общее число рефералов
                - paid_referrals_count (int): Число рефералов с бонусом
                - referral_conversion (float): Конверсия (paid / total)

        Raises
            APIClientError: Если ответ API невалиден.

        """
        data = await self.client.get(f"/api/users/{telegram_id}/referrals")
        return SUserWithReferralStats.model_validate(data)
