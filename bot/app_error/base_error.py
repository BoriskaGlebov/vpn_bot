from bot.app_error.schema import ErrorDetail


class AppError(Exception):
    """Базовое приложение-ориентированное исключение.

    Args:
        message (str): Описание ошибки.
        cause (Exception | None): Исходное исключение.

    """

    def __init__(self, error: ErrorDetail, *, cause: Exception | None = None) -> None:
        self.error = error

        super().__init__(f"[{error.code}] {error.message}")
        self.cause = cause

    def __str__(self) -> str:
        """Строковое представление об ошибке."""
        base = super().__str__()
        if self.cause:
            return f"{base} (cause: {self.cause})"
        return base


class MessageNotFoundError(AppError):
    """Ошибка сообщения для редактирования не найдено."""

    def __init__(self) -> None:
        super().__init__(
            ErrorDetail(
                code="message_not_found",
                message="Сообщение для редактирования не найдено",
            )
        )


class UserNotFoundError(AppError):
    def __init__(self, tg_id: int) -> None:
        super().__init__(
            ErrorDetail(
                code="user_not_found",
                message=f"Пользователь с Telegram ID {tg_id} не найден",
                details={
                    "tg_id": tg_id,
                },
            )
        )

        self.tg_id = tg_id


class SubscriptionNotFoundError(AppError):
    def __init__(self, tg_id: int) -> None:
        super().__init__(
            ErrorDetail(
                code="subscription_not_found",
                message=f"У пользователя {tg_id} нет активной подписки",
                details={
                    "tg_id": tg_id,
                },
            )
        )

        self.tg_id = tg_id


class VPNLimitError(AppError):
    def __init__(
        self,
        tg_id: int,
        limit: int,
        username: str = "",
    ) -> None:
        super().__init__(
            ErrorDetail(
                code="vpn_limit_reached",
                message=f"Пользователь достиг лимита VPN-конфигов ({limit})",
                details={
                    "tg_id": tg_id,
                    "limit": limit,
                    "username": username,
                },
            )
        )

        self.tg_id = tg_id
        self.limit = limit
        self.username = username