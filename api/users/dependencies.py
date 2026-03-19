from api.users.services import UserService


async def get_user_service() -> UserService:
    """Depends для UserService."""
    return UserService()
