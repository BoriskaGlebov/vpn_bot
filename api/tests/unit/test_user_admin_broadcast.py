"""Действие «Отправить рассылку» в UserAdmin (#385): форма + отправка боту.

`Request` подделывается без реального ASGI-стека. Аутентификация SQLAdmin
(`login_required`, которым оборачиваются `@action`/`@expose`) сама себя
пропускает: голый `UserAdmin()` без `_admin_ref` (он выставляется только при
регистрации через `admin.add_model_view`) не имеет `authentication_backend` —
тот же приём, что и в `test_user_admin.py` для `on_model_delete`.
`admin.templates` подделывается лёгким фейком вместо реального Jinja2-рендера:
важно, какой шаблон и с каким контекстом выбран, а не HTML-разметка.
"""

from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import FormData, QueryParams
from starlette.requests import Request

from api.users.admin import UserAdmin


class FakeTemplateResponse:
    def __init__(self, request: Any, template: str, context: dict[str, Any]) -> None:
        self.request = request
        self.template = template
        self.context = context


class FakeTemplates:
    async def TemplateResponse(
        self, request: Any, template: str, context: dict[str, Any]
    ) -> FakeTemplateResponse:
        return FakeTemplateResponse(request, template, context)


@pytest.fixture
def admin() -> UserAdmin:
    instance = UserAdmin()
    instance.templates = FakeTemplates()  # type: ignore[assignment]
    return instance


def patch_async_session(
    monkeypatch: pytest.MonkeyPatch, telegram_ids: list[int]
) -> None:
    """Подменяет `api.users.admin.async_session` фейковой сессией.

    `session.scalars(...)` возвращает заранее заданный список telegram_id —
    без реального похода в БД, аналогично `mock_execute_result` в
    `api/tests/conftest.py`.
    """
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = telegram_ids
    session.scalars = AsyncMock(return_value=result)

    @asynccontextmanager
    async def fake_async_session() -> Any:
        yield session

    monkeypatch.setattr("api.users.admin.async_session", fake_async_session)


def make_request(
    query: dict[str, str] | None = None, form: dict[str, str] | None = None
) -> AsyncMock:
    request = AsyncMock(spec=Request)
    request.query_params = QueryParams(query or {})
    request.form = AsyncMock(return_value=FormData(form or {}))
    request.url_for = MagicMock(
        side_effect=lambda name, **kwargs: f"http://testserver/admin/{name}"
    )
    return request


@pytest.mark.asyncio
async def test_send_broadcast_form_shows_recipients_count(admin, monkeypatch):
    patch_async_session(monkeypatch, [111, 222])
    request = make_request(query={"pks": "1,2"})

    response = await admin.send_broadcast_form(request)

    assert response.template == "admin/broadcast_form.html"
    assert response.context["recipients_count"] == 2
    assert response.context["pks"] == "1,2"


@pytest.mark.asyncio
async def test_send_broadcast_form_zero_recipients(admin, monkeypatch):
    patch_async_session(monkeypatch, [])
    request = make_request(query={"pks": "1,2"})

    response = await admin.send_broadcast_form(request)

    assert response.context["recipients_count"] == 0


@pytest.mark.asyncio
async def test_send_broadcast_sends_to_bot_and_shows_confirmation(admin, monkeypatch):
    patch_async_session(monkeypatch, [111, 222])
    client = AsyncMock()
    client.send_broadcast.return_value = 2
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    request = make_request(form={"pks": "1,2", "text": "Привет!"})

    response = await admin.send_broadcast(request)

    client.send_broadcast.assert_awaited_once_with("Привет!", [111, 222])
    assert response.template == "admin/broadcast_sent.html"
    assert response.context["recipients_count"] == 2


@pytest.mark.asyncio
async def test_send_broadcast_empty_text_rerenders_form_without_calling_bot(
    admin, monkeypatch
):
    patch_async_session(monkeypatch, [111, 222])
    client = AsyncMock()
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    request = make_request(form={"pks": "1,2", "text": "   "})

    response = await admin.send_broadcast(request)

    client.send_broadcast.assert_not_awaited()
    assert response.template == "admin/broadcast_form.html"
    assert "пустым" in response.context["error"]


@pytest.mark.asyncio
async def test_send_broadcast_no_recipients_rerenders_form_without_calling_bot(
    admin, monkeypatch
):
    patch_async_session(monkeypatch, [])
    client = AsyncMock()
    monkeypatch.setattr("api.users.admin.get_bot_channel_client", lambda: client)

    request = make_request(form={"pks": "", "text": "Привет!"})

    response = await admin.send_broadcast(request)

    client.send_broadcast.assert_not_awaited()
    assert response.template == "admin/broadcast_form.html"
    assert "получателей" in response.context["error"]


@pytest.mark.asyncio
async def test_parse_pks_ignores_blank_and_non_numeric_tokens():
    from api.users.admin import _parse_pks

    assert _parse_pks("1,2,3") == [1, 2, 3]
    assert _parse_pks("") == []
    assert _parse_pks("1,,abc,2") == [1, 2]
