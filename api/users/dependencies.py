from api.users.services import UserService


async def get_user_service() -> UserService:
    """Возвращает экземпляр UserService."""
    return UserService()
