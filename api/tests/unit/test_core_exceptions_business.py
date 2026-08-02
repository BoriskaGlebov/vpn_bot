import json

import pytest
from fastapi import Request

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    ReferralError,
    ReferralNotFoundError,
    SubscriptionNotFoundError,
    TrialAlreadyUsedError,
    UserNotFoundError,
    VPNLimitError,
)
from api.core.exceptions.handlers.business import app_error_handler


class DummyRequest(Request):
    """Минимальный Request для тестов."""

    def __init__(self, path: str = "/test"):
        scope = {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
        }
        super().__init__(scope)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "status_code"),
    [
        (UserNotFoundError(tg_id=123), 404),
        (SubscriptionNotFoundError(user_id=42, username="test"), 404),
        (ActiveSubscriptionExistsError(user_id=42, username="test"), 409),
        (TrialAlreadyUsedError(user_id=42, username="test"), 409),
        (ReferralNotFoundError(invited_user_id=42, username="test"), 404),
        (ReferralError("Generic referral error"), 400),
        (VPNLimitError(user_id=99, limit=5, username="test"), 409),
    ],
)
async def test_app_error_handler_returns_expected_status(
    exception,
    status_code,
):
    """Каждый доменный AppError мапится в свой HTTP-статус и тело ошибки."""
    request = DummyRequest()

    response = await app_error_handler(request, exception)

    assert response.status_code == status_code

    payload = json.loads(response.body)

    assert "error" in payload
    assert payload["error"]["code"] == exception.code
    assert payload["error"]["message"] == exception.message


@pytest.mark.asyncio
async def test_app_error_handler_unexpected_exception():
    """Исключение, не являющееся AppError, всё равно даёт корректный 500-ответ.

    Текст исключения (`str(exc)`) не должен попадать в тело ответа клиенту —
    он может содержать внутренние детали приложения (пути, куски SQL,
    содержимое ошибок соединения и т.п.). Полный текст доступен только
    в логах через `logger.exception`.
    """
    request = DummyRequest()

    response = await app_error_handler(
        request,
        ValueError("boom, contains secret db connection string"),
    )

    assert response.status_code == 500

    payload = json.loads(response.body)

    assert payload["error"]["code"] == "internal_error"
    assert payload["error"]["details"]["exc_type"] == "ValueError"
    assert payload["error"]["message"] == "Internal server error"
    assert "boom" not in payload["error"]["message"]
