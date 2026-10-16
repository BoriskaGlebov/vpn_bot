import hashlib
import secrets
from base64 import b64decode, b64encode
from collections.abc import Mapping
from typing import Any

from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from api.core.config import settings_api

_HASH_ALGORITHM = "sha256"
_HASH_ITERATIONS = 310_000  # рекомендация OWASP для PBKDF2-HMAC-SHA256 (2023)

# "." как разделитель полей, а не "$": значение хеша проходит через
# GitHub Secret -> bash heredoc в деплой-скрипте -> Docker Compose env_file.
# Docker Compose интерполирует "$VAR"/"${VAR}" внутри значений, загруженных
# через env_file (не только в самом docker-compose.yml), и при "$"-разделителе
# части хеша после каждого "$" воспринимались как имена переменных и тихо
# заменялись на пустую строку — хеш обрезался молча, без ошибки при деплое.
# "." не используется в алфавите base64 (ни стандартном, ни url-safe) и
# ничего не значит ни для bash, ни для Compose.
_FIELD_SEPARATOR = "."


def hash_password(password: str) -> str:
    """Хеширует пароль для `ADMIN_PANEL_PASSWORD_HASH` (PBKDF2-HMAC-SHA256, случайная соль).

    Используется один раз при генерации значения переменной окружения, а не
    в runtime-коде. Пример::

        python -c "from api.users.auth_admin import hash_password; print(hash_password('...'))"

    Args:
        password: пароль в открытом виде.

    Returns
        str: `pbkdf2_sha256.<iterations>.<salt_b64>.<hash_b64>`.

    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        _HASH_ALGORITHM, password.encode(), salt, _HASH_ITERATIONS
    )
    sep = _FIELD_SEPARATOR
    return (
        f"pbkdf2_sha256{sep}{_HASH_ITERATIONS}"
        f"{sep}{b64encode(salt).decode()}{sep}{b64encode(digest).decode()}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    """Проверяет пароль против хеша из `hash_password`, тайминг-устойчиво.

    Args:
        password: пароль в открытом виде, полученный из формы входа.
        encoded_hash: хеш в формате `hash_password` (может быть пустой строкой,
            если `ADMIN_PANEL_PASSWORD_HASH` не задан — тогда всегда `False`).

    Returns
        bool: True, если пароль соответствует хешу.

    """
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded_hash.split(
            _FIELD_SEPARATOR
        )
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    salt = b64decode(salt_b64)
    expected_digest = b64decode(digest_b64)
    actual_digest = hashlib.pbkdf2_hmac(
        _HASH_ALGORITHM, password.encode(), salt, int(iterations)
    )

    return secrets.compare_digest(actual_digest, expected_digest)


class AdminAuth(AuthenticationBackend):
    """Простая session-based авторизация для SQLAdmin.

    Логин и пароль — отдельные учётные данные панели (`ADMIN_PANEL_USER` /
    `ADMIN_PANEL_PASSWORD_HASH`), не связанные с паролем PostgreSQL: раньше
    вход совпадал с учётными данными БД, то есть пароль от прямого доступа к
    базе вводился в веб-форму и утекал в менеджер паролей браузера.

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

        password_hash = settings_api.admin_panel_password_hash.get_secret_value()

        if not password_hash:
            return False

        if secrets.compare_digest(
            username, settings_api.admin_panel_user
        ) and verify_password(password, password_hash):
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
