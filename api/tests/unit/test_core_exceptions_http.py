import json

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.core.exceptions.handlers.http import (
    database_exception_handler,
    request_validation_handler,
)


class DummyRequest(Request):
    """Минимальный ASGI Request для тестов."""

    def __init__(self, path: str = "/test"):
        scope = {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
        }
        super().__init__(scope)


@pytest.mark.asyncio
async def test_request_validation_handler():
    """Ошибка валидации pydantic оборачивается в единый JSON-формат ошибки."""
    request = DummyRequest("/users")

    errors = [
        {
            "loc": ("body", "email"),
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]

    exc = RequestValidationError(errors)

    response = await request_validation_handler(request, exc)

    assert response.status_code == 422

    data = json.loads(response.body)

    assert data["error"]["code"] == "validation_error"
    assert "Ошибка валидации запроса" in data["error"]["message"]

    assert data["error"]["details"]["exc_type"] == "RequestValidationError"
    assert data["error"]["details"]["errors"] == [
        {
            **errors[0],
            "loc": list(errors[0]["loc"]),
        }
    ]


@pytest.mark.asyncio
async def test_request_validation_handler_multiple_errors():
    """Несколько ошибок валидации попадают в details.errors списком."""
    request = DummyRequest("/users")

    errors = [
        {
            "loc": ("body", "email"),
            "msg": "field required",
            "type": "value_error.missing",
        },
        {
            "loc": ("query", "limit"),
            "msg": "value is not a valid integer",
            "type": "type_error.integer",
        },
    ]

    exc = RequestValidationError(errors)

    response = await request_validation_handler(request, exc)

    assert response.status_code == 422

    data = json.loads(response.body)

    assert data["error"]["code"] == "validation_error"
    assert len(data["error"]["details"]["errors"]) == 2


@pytest.mark.asyncio
async def test_request_validation_handler_strips_input_and_url(monkeypatch):
    """details.errors не содержит input (присланное значение, может быть
    паролем/секретом) и url (версия pydantic) — только type/loc/msg (#240).
    """
    request = DummyRequest("/users/register")

    # pydantic реально кладёт input/url в errors() — воспроизводим это явно,
    # а не полагаемся на то, что RequestValidationError сама их добавит.
    raw_errors = [
        {
            "type": "string_too_short",
            "loc": ("body", "password"),
            "msg": "String should have at least 8 characters",
            "input": "secret",
            "url": "https://errors.pydantic.dev/2.11/v/string_too_short",
        }
    ]
    exc = RequestValidationError(raw_errors)
    monkeypatch.setattr(exc, "errors", lambda: raw_errors)

    response = await request_validation_handler(request, exc)

    data = json.loads(response.body)
    (error,) = data["error"]["details"]["errors"]

    assert set(error.keys()) == {"type", "loc", "msg"}
    assert "secret" not in json.dumps(data)
    assert "errors.pydantic.dev" not in json.dumps(data)


@pytest.mark.asyncio
async def test_request_validation_handler_message_has_no_repr_or_values():
    """message — короткий текст без repr(exc) и без присланных значений (#240).

    Раньше `f"Ошибка валидации запроса {repr(exc)}"` отправлял пользователю
    в Telegram список ошибок pydantic целиком, включая присланные значения.
    """
    request = DummyRequest("/users/register")

    errors = [
        {
            "loc": ("body", "password"),
            "msg": "String should have at least 8 characters",
            "type": "string_too_short",
            "input": "my-secret-password",
        }
    ]
    exc = RequestValidationError(errors)

    response = await request_validation_handler(request, exc)

    data = json.loads(response.body)
    message = data["error"]["message"]

    assert message == "Ошибка валидации запроса"
    assert "my-secret-password" not in message
    assert "RequestValidationError(" not in message


@pytest.mark.asyncio
async def test_database_exception_handler():
    """SQLAlchemyError не протекает наружу, а даёт единый 500-формат без деталей БД."""
    request = DummyRequest("/db")

    exc = SQLAlchemyError("DB connection failed")

    response = await database_exception_handler(request, exc)

    assert response.status_code == 500

    data = json.loads(response.body)

    assert data == {
        "error": {
            "code": "database_error",
            "message": "Внутренняя ошибка базы данных",
            "details": {
                "exc_type": "SQLAlchemyError",
            },
        }
    }


@pytest.mark.asyncio
async def test_database_exception_handler_contains_exception_type():
    """Ответ содержит исходный тип исключения в details.exc_type для диагностики."""
    request = DummyRequest("/db")

    exc = SQLAlchemyError("some db error")

    response = await database_exception_handler(request, exc)

    data = json.loads(response.body)

    assert data["error"]["code"] == "database_error"
    assert data["error"]["details"]["exc_type"] == "SQLAlchemyError"
