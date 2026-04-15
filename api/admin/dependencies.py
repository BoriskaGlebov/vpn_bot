from typing import Annotated

from fastapi.params import Depends

from api.admin.services import AdminService
from api.app_error.api_error import AdminNotFoundHeaderError
from api.core.dependencies import get_current_user
from api.users.models import User
from shared.enums.admin_enum import RoleEnum


def get_admin_service() -> AdminService:
    """Depends для AdminService."""
    return AdminService()


def check_admin_role(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Проверяет, что текущий пользователь имеет роль администратора.

    Args:
        user (User): Текущий пользователь, полученный через Depends(get_current_user).

    Raises
        AdminNotFoundHeaderError: Если пользователь не является администратором.

    Returns
        User: Пользователь с правами администратора.

    """
    if user.role.name == RoleEnum.ADMIN.value:
        return user
    else:
        raise AdminNotFoundHeaderError(tg_id=user.telegram_id)
