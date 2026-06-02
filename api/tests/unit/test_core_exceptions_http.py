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
async def test_database_exception_handler():
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
    request = DummyRequest("/db")

    exc = SQLAlchemyError("some db error")

    response = await database_exception_handler(request, exc)

    data = json.loads(response.body)

    assert data["error"]["code"] == "database_error"
    assert data["error"]["details"]["exc_type"] == "SQLAlchemyError"
