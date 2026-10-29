"""Регрессия: SQLAdmin монтирует собственное Starlette-приложение со своим
`exception_handlers` — обработчики, зарегистрированные на внешнем `app`
(`api/main.py`), на него не распространяются. Без явной регистрации на
`admin.admin` любое исключение (кроме `HTTPException`) из `on_model_delete`/
`on_model_change` ловится внутренним `ServerErrorMiddleware` как generic 500
и ПЕРЕБРАСЫВАЕТСЯ дальше — оно всплывает через внешние `BaseHTTPMiddleware`
и падает с `RuntimeError("Caught handled exception, but response already
started")` вместо внятного ответа (#290). Проверено на реальном `app` из
`api.main`, где фикс уже применён (`admin.admin.add_exception_handler(...)`).
"""

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from api.app_error.base_error import AppError
from api.main import admin


class _PassthroughMiddleware(BaseHTTPMiddleware):
    """Мимикрирует BaseHTTPMiddleware-прослойки api/main.py (RequestLoggingMiddleware и т.п.)."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)


async def _boom(request: Request) -> None:
    raise AppError("буммм")


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"error": str(exc)}, status_code=502)


def _build_outer_app(register_on_inner: bool) -> Starlette:
    inner = Starlette(routes=[Route("/boom", _boom)])
    if register_on_inner:
        inner.add_exception_handler(AppError, _app_error_handler)

    # Внешний app в api/main.py регистрирует AppError-обработчик ВСЕГДА —
    # именно попытка ЭТОГО обработчика отправить свой ответ поверх уже
    # отправленного внутренним ServerErrorMiddleware и роняет запрос.
    outer = Starlette(routes=[])
    outer.add_exception_handler(AppError, _app_error_handler)
    outer.mount("/admin", inner)
    outer.add_middleware(_PassthroughMiddleware)
    return outer


def test_unregistered_inner_handler_crashes_through_outer_middleware():
    """Без регистрации на вложенном приложении AppError пробивает его
    ServerErrorMiddleware и обрушивает запрос тем же RuntimeError, что
    увидел админ при удалении пользователя.
    """
    client = TestClient(_build_outer_app(register_on_inner=False))

    with pytest.raises(RuntimeError, match="response already started"):
        client.get("/admin/boom")


def test_registered_inner_handler_returns_clean_response():
    """После regитрации обработчика на вложенном приложении тот же сценарий
    отдаёт чистый JSON вместо краха — именно так устроен фикс в api/main.py.
    """
    client = TestClient(_build_outer_app(register_on_inner=True))

    response = client.get("/admin/boom")

    assert response.status_code == 502
    assert response.json() == {"error": "буммм"}


def test_real_admin_app_has_handlers_registered_on_inner_starlette_app():
    """Регрессия на сам фикс: `admin.admin` (внутреннее Starlette-приложение
    SQLAdmin, смонтированное в `api/main.py`) должен иметь обработчики для
    AppError/APIError/Exception — иначе #290 воспроизводится снова на
    реальном `app`.
    """
    assert AppError in admin.admin.exception_handlers
    assert Exception in admin.admin.exception_handlers
