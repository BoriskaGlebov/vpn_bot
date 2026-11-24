from datetime import datetime

from bot.app_error.base_error import PanelError


class RemnawaveError(PanelError):
    """Базовая ошибка при работе с панелью Remnawave.

    Наследуется от `PanelError` (который в свою очередь наследуется от
    `AppError`), чтобы попадать в общий `ErrorHandlerMiddleware`
    (который распознаёт только `AppError`/`APIClientError`) и корректно
    превращаться в `ErrorEnvelope` вместо generic "unexpected_error".

    Args:
        message (str): Описание ошибки.
        details (dict | None): Дополнительные диагностические данные.
        cause (Optional[Exception]): Исходное исключение, если это обёртка.

    """

    code: str = "remnawave_error"
    status_code: int = 502


class RemnawaveAuthError(RemnawaveError):
    """Не удалось авторизоваться в панели Remnawave (401/403).

    Args:
        reason (str): Причина отказа, присланная панелью.

    """

    code = "remnawave_auth_error"
    status_code = 401

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            message=f"Не удалось авторизоваться в Remnawave: {reason}",
            details={"reason": reason},
        )
        self.reason = reason


class RemnawaveUserNotFoundError(RemnawaveError):
    """Пользователь не найден на панели Remnawave (404).

    Args:
        identifier (str): Идентификатор пользователя (uuid/telegramId/username),
            по которому выполнялся поиск.

    """

    code = "remnawave_user_not_found"
    status_code = 404

    def __init__(self, identifier: str) -> None:
        super().__init__(
            message=f"Пользователь '{identifier}' не найден на панели Remnawave",
            details={"identifier": identifier},
        )
        self.identifier = identifier


class RemnawaveRequestError(RemnawaveError):
    """Панель Remnawave ответила ошибкой на произвольный запрос (4xx/5xx).

    Args:
        action (str): Название операции, в рамках которой произошла ошибка
            (например, "create_user", "update_user").
        reason (str): Причина отказа, присланная панелью.
        status_code (int): HTTP-статус ответа панели.

    """

    code = "remnawave_request_error"

    def __init__(self, action: str, reason: str = "", status_code: int = 502) -> None:
        super().__init__(
            message=f"Remnawave вернул ошибку при выполнении '{action}': {reason}",
            details={"action": action, "reason": reason},
        )
        self.status_code = status_code
        self.action = action
        self.reason = reason


class RemnawaveInvalidExpiryError(RemnawaveError):
    """Некорректный момент продления подписки — `expires_at` не в будущем.

    Args:
        expires_at (datetime): Переданный момент окончания действия.

    """

    code = "remnawave_invalid_expiry"
    status_code = 400

    def __init__(self, expires_at: datetime) -> None:
        super().__init__(
            message=f"Некорректный момент продления подписки: {expires_at}",
            details={"expires_at": expires_at.isoformat()},
        )
        self.expires_at = expires_at
