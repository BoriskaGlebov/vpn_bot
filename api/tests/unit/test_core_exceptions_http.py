import json

import pytest
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.core.exceptions.handlers.http import (
    database_exception_handler,
    request_validation_handler,
)


def normalize_errors(errors):
    return [
        {
            **err,
            "loc": list(err["loc"]),
        }
        for err in errors
    ]


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

    assert data["detail"] == "Ошибка валидации запроса"
    assert data["errors"] == normalize_errors(errors)


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

    assert len(data["errors"]) == 2
    assert data["errors"] == normalize_errors(errors)


@pytest.mark.asyncio
async def test_database_exception_handler():
    request = DummyRequest("/db")

    exc = SQLAlchemyError("DB connection failed")

    response = await database_exception_handler(request, exc)

    assert response.status_code == 500

    data = json.loads(response.body)

    assert data == {
        "detail": "Ошибка работы с базой данных",
    }


@pytest.mark.asyncio
async def test_database_exception_handler_does_not_leak_details():
    request = DummyRequest("/db")

    exc = SQLAlchemyError("sensitive internal error")

    response = await database_exception_handler(request, exc)

    data = json.loads(response.body)

    # убеждаемся, что текст ошибки НЕ попал в ответ
    assert "sensitive" not in str(data)
