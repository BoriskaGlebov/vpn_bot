import pytest

from bot.app_error.api_error import (
    APIClientConflictError,
    APIClientConnectionError,
    APIClientError,
    APIClientForbiddenError,
    APIClientHTTPError,
    APIClientNotFoundError,
    APIClientUnauthorizedError,
    APIClientValidationError,
    map_http_error,
)
from bot.app_error.schema import ErrorDetail

# =========================
# map_http_error
# =========================


@pytest.mark.parametrize(
    ("status_code", "expected_cls"),
    [
        (401, APIClientUnauthorizedError),
        (403, APIClientForbiddenError),
        (404, APIClientNotFoundError),
        (409, APIClientConflictError),
        (422, APIClientValidationError),
        (500, APIClientHTTPError),  # default case
    ],
)
def test_map_http_error_returns_correct_type(status_code, expected_cls):
    response_body = {"error": {"code": "some_error", "message": "some message"}}
    err = map_http_error(status_code, response_body)

    assert isinstance(err, expected_cls)
    assert err.status_code == status_code
    assert err.error.code == "some_error"
    assert err.error.message == "some message"


@pytest.mark.parametrize(
    ("response_body", "expected_message"),
    [
        (
            {"error": {"code": "not_found", "message": "Деталей нет."}},
            "[not_found] Деталей нет.",
        ),
        (
            {"error": {"code": "not_found", "message": "Not Found"}},
            "[not_found] Not Found",
        ),
    ],
)
def test_map_http_error_message_format(response_body, expected_message):
    err = map_http_error(404, response_body)

    assert str(err) == expected_message


# =========================
# APIClientError.__str__
# =========================


def test_api_client_error_str_without_cause():
    err = APIClientError(ErrorDetail(code="some_error", message="some error"))

    assert str(err) == "[some_error] some error"


def test_api_client_error_str_with_cause():
    cause = ValueError("boom")
    err = APIClientError(
        ErrorDetail(code="wrapper_error", message="wrapper error"), cause=cause
    )

    assert str(err) == "[wrapper_error] wrapper error (cause: boom)"


# =========================
# APIClientConnectionError
# =========================


def test_connection_error_default_message():
    err = APIClientConnectionError()

    assert str(err) == "[connection_error] ⚠️ Не удалось подключиться к API"


def test_connection_error_with_cause():
    cause = RuntimeError("network down")
    err = APIClientConnectionError(cause=cause)

    assert (
        str(err)
        == "[connection_error] ⚠️ Не удалось подключиться к API (cause: network down)"
    )
    assert err.cause is cause


# =========================
# HTTP error inheritance sanity
# =========================


@pytest.mark.parametrize(
    "exc_cls",
    [
        APIClientUnauthorizedError,
        APIClientForbiddenError,
        APIClientNotFoundError,
        APIClientValidationError,
        APIClientConflictError,
    ],
)
def test_http_error_inheritance(exc_cls):
    err = exc_cls(400, ErrorDetail(code="some_error", message="detail"))

    assert isinstance(err, APIClientHTTPError)
    assert err.status_code == 400
    assert err.error.code == "some_error"
    assert err.error.message == "detail"
