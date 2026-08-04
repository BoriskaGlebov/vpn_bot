from typing import Any

from bot.app_error.base_error import AppError


class ThreeXUIError(AppError):
    """Базовая ошибка при работе с панелью 3x-ui.

    Наследуется от `AppError`, чтобы попадать в общий `ErrorHandlerMiddleware`
    (который распознаёт только `AppError`/`APIClientError`) и корректно
    превращаться в `ErrorEnvelope` вместо generic "unexpected_error".

    От ошибок `bot.app_error.api_error` (`APIClientError` и наследники)
    отличается тем, что не привязана к формату ответа нашего собственного
    `api/` (`ErrorEnvelope`) — панель 3x-ui отвечает своим форматом
    (`{"success": bool, "msg": str, "obj": ...}`), который туда не мапится.

    Args:
        message (str): Описание ошибки.
        details (dict | None): Дополнительные диагностические данные.
        cause (Optional[Exception]): Исходное исключение, если это обёртка.

    """

    code: str = "three_x_ui_error"
    status_code: int = 502


class ThreeXUIAuthError(ThreeXUIError):
    """Не удалось авторизоваться в панели 3x-ui.

    Args:
        username (str): Логин, под которым выполнялась попытка авторизации.
        reason (str): Причина отказа (поле `msg` из ответа панели).

    """

    code = "three_x_ui_auth_error"

    def __init__(self, username: str, reason: str = "") -> None:
        super().__init__(
            message=f"Не удалось авторизоваться в 3x-ui под {username}: {reason}",
            details={"username": username, "reason": reason},
        )
        self.username = username
        self.reason = reason


class ThreeXUIRequestError(ThreeXUIError):
    """Панель 3x-ui ответила `success: false` на запрос.

    Args:
        action (str): Название операции, в рамках которой произошла ошибка
            (например, "add_client", "update_client").
        reason (str): Причина отказа (поле `msg` из ответа панели).

    """

    code = "three_x_ui_request_error"

    def __init__(self, action: str, reason: str = "") -> None:
        super().__init__(
            message=f"3x-ui вернул ошибку при выполнении '{action}': {reason}",
            details={"action": action, "reason": reason},
        )
        self.action = action
        self.reason = reason


class ThreeXUIInboundNotFoundError(ThreeXUIError):
    """Не все ожидаемые inbound-конфигурации найдены на панели.

    Args:
        expected (int): Количество ожидаемых inbound (из настроек ноды).
        found (list[Any]): Фактически найденные inbound.

    """

    code = "three_x_ui_inbound_not_found"

    def __init__(self, expected: int, found: list[Any]) -> None:
        super().__init__(
            message=f"Не все inbound найдены: ожидалось {expected}, найдено {len(found)}",
            details={"expected": expected, "found": found},
        )
        self.expected = expected
        self.found = found


class ThreeXUIConfigNotFoundError(ThreeXUIError):
    """Ни один из указанных config_id клиента не найден ни в одном inbound ноды.

    Args:
        config_ids (list[str]): Идентификаторы конфигураций, которые не были найдены.

    """

    code = "three_x_ui_config_not_found"
    status_code = 404

    def __init__(self, config_ids: list[str]) -> None:
        super().__init__(
            message=f"Конфигурации не найдены на панели 3x-ui: {config_ids}",
            details={"config_ids": config_ids},
        )
        self.config_ids = config_ids


class ThreeXUIInvalidExpiryError(ThreeXUIError):
    """Некорректное количество дней для продления подписки (`days <= 0`).

    Args:
        days (int): Переданное количество дней.

    """

    code = "three_x_ui_invalid_expiry"
    status_code = 400

    def __init__(self, days: int) -> None:
        super().__init__(
            message=f"Некорректное количество дней для продления подписки: {days}",
            details={"days": days},
        )
        self.days = days
