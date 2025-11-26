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


class SubscriptionNotFoundError(AppError):
    """У пользователя нет подписки."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"У пользователя {user_id} нет подписки / не активна.")
        self.user_id = user_id


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
