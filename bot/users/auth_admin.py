from collections.abc import Mapping
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from bot.config import settings_db


class AdminAuth(AuthenticationBackend):
    """Простая session-based авторизация для SQLAdmin.

    Авторизация выполняется через сравнение логина и пароля,
    полученных из формы входа, со значениями из конфигурации.

    После успешной аутентификации в сессию записывается флаг `admin`,
    который далее используется методом `authenticate`.
    """

    async def login(self, request: Request) -> bool:
        """Проверяет логин и пароль пользователя.

        Args:
            request: Входящий HTTP-запрос Starlette.

        Returns
            True, если авторизация успешна.
            False, если учетные данные некорректны.

        """
        form: Mapping[str, Any] = await request.form()

        username = form.get("username")
        password = form.get("password")

        if not isinstance(username, str) or not isinstance(password, str):
            return False

        if (
            username == settings_db.db_user
            and password == settings_db.db_password.get_secret_value()
        ):
            request.session.update({"admin": True})
            return True

        return False

    async def logout(self, request: Request) -> bool:
        """Выполняет выход пользователя из системы.

        Args:
            request: Входящий HTTP-запрос Starlette.

        Returns
            True после очистки сессии.

        """
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> bool:
        """Проверяет, авторизован ли пользователь.

        Метод вызывается перед обработкой каждого запроса
        к административной панели.

        Args:
            request: Входящий HTTP-запрос Starlette.

        Returns
            True, если пользователь ранее прошёл авторизацию.
            False в противном случае.

        """
        is_admin = request.session.get("admin")
        return bool(is_admin)
