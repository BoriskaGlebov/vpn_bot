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

# =========================
# map_http_error
# =========================


@pytest.mark.parametrize(
    ("status_code", "detail", "expected_cls"),
    [
        (401, "unauthorized", APIClientUnauthorizedError),
        (403, "forbidden", APIClientForbiddenError),
        (404, "not found", APIClientNotFoundError),
        (409, "conflict", APIClientConflictError),
        (422, "validation error", APIClientValidationError),
        (500, "server error", APIClientHTTPError),  # default case
    ],
)
def test_map_http_error_returns_correct_type(status_code, detail, expected_cls):
    err = map_http_error(status_code, detail)

    assert isinstance(err, expected_cls)
    assert err.status_code == status_code
    assert err.detail == detail


@pytest.mark.parametrize(
    ("status_code", "detail", "expected_message"),
    [
        (404, None, "HTTP 404: Деталей нет."),
        (404, "Not Found", "HTTP 404: Not Found"),
    ],
)
def test_map_http_error_message_format(status_code, detail, expected_message):
    err = map_http_error(status_code, detail)

    assert str(err) == expected_message


# =========================
# APIClientError.__str__
# =========================


def test_api_client_error_str_without_cause():
    err = APIClientError("some error")

    assert str(err) == "some error"


def test_api_client_error_str_with_cause():
    cause = ValueError("boom")
    err = APIClientError("wrapper error", cause=cause)

    assert str(err) == "wrapper error (cause: boom)"


# =========================
# APIClientConnectionError
# =========================


def test_connection_error_default_message():
    err = APIClientConnectionError()

    assert str(err) == "Ошибка соединения с API"


def test_connection_error_custom_message_and_cause():
    cause = RuntimeError("network down")
    err = APIClientConnectionError("custom message", cause=cause)

    assert str(err) == "custom message (cause: network down)"
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
    err = exc_cls(400, "detail")

    assert isinstance(err, APIClientHTTPError)
    assert err.status_code == 400
    assert err.detail == "detail"
