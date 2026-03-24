class AppError(Exception):
    """Базовое приложение-ориентированное исключение.

    Args:
        message (str): Описание ошибки.
        cause (Exception | None): Исходное исключение.

    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        """Строковое представление об ошибке."""
        base = super().__str__()
        if self.cause:
            return f"{base} (cause: {self.cause})"
        return base


class UserNotFoundError(AppError):
    """Пользователь не найден."""

    def __init__(self, tg_id: int) -> None:
        super().__init__(message=f"Пользователь с Telegram ID {tg_id} не найден.")
        self.tg_id = tg_id


class RoleNotFoundError(AppError):
    """Роль не найден."""

    def __init__(self, role_name: str) -> None:
        super().__init__(message=f"Роль пользователя  {role_name} не найдена.")
        self.role_name = role_name


class SubscriptionNotFoundError(AppError):
    """У пользователя нет подписки."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"У пользователя {user_id} нет подписки / не активна.")
        self.user_id = user_id


class ActiveSubscriptionExistsError(AppError):
    """У пользователя уже есть активная подписка."""

    def __init__(self) -> None:
        super().__init__("У пользователя уже есть активная подписка")


class TrialAlreadyUsedError(AppError):
    """Пробный период уже использован."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message=message if message else "Пробный период уже был использован"
        )


class VPNLimitError(AppError):
    """Пользователь достиг лимита VPN-конфигов.

    Args:
        user_id (int): ID пользователя.
        limit (int): Максимальное количество конфигов.

    """

    def __init__(self, user_id: int, limit: int, username: str = "") -> None:
        super().__init__(
            f"Пользователь {user_id} достиг лимита ({limit}) конфигов.\n@{username}"
        )
        self.user_id = user_id
        self.username = username
        self.limit = limit
