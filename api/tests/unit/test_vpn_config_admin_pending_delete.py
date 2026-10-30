"""Действие «Пометить на удаление» в VPNConfigAdmin: форма + причина + bulk-update.

`Request` подделывается без реального ASGI-стека, `admin.templates` —
лёгким фейком вместо реального Jinja2-рендера, по тому же приёму, что и
`test_user_admin_broadcast.py` (#385) для `UserAdmin.send_broadcast`.
"""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.datastructures import FormData, QueryParams
from starlette.requests import Request

from api.vpn.admin import VPNConfigAdmin
from api.vpn.dao import VPNConfigDAO
from api.vpn.models import VPNConfigStatus


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
def admin() -> VPNConfigAdmin:
    instance = VPNConfigAdmin()
    instance.templates = FakeTemplates()  # type: ignore[assignment]
    return instance


def make_config(
    id_: int, status: VPNConfigStatus, username: str | None = "user"
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id_,
        file_name=f"config{id_}.conf",
        node_name="main",
        status=status,
        user=SimpleNamespace(username=username, telegram_id=1000 + id_),
    )


def patch_async_session(monkeypatch: pytest.MonkeyPatch, configs: list[Any]) -> None:
    """Подменяет `api.vpn.admin.async_session` фейковой сессией.

    `session.scalars(...)` возвращает заранее заданный список конфигов —
    без реального похода в БД, аналогично `patch_async_session` в
    `test_user_admin_broadcast.py`.
    """
    session = MagicMock()
    result = MagicMock()
    result.all.return_value = configs
    session.scalars = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    @asynccontextmanager
    async def fake_async_session() -> Any:
        yield session

    monkeypatch.setattr("api.vpn.admin.async_session", fake_async_session)


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
async def test_mark_pending_delete_form_counts_only_active(admin, monkeypatch):
    """Форма считает "реально переведётся" только по ACTIVE среди отмеченных."""
    configs = [
        make_config(1, VPNConfigStatus.ACTIVE),
        make_config(2, VPNConfigStatus.ACTIVE),
        make_config(3, VPNConfigStatus.PENDING_DELETE),
    ]
    patch_async_session(monkeypatch, configs)
    request = make_request(query={"pks": "1,2,3"})

    response = await admin.mark_pending_delete_form(request)

    assert response.template == "admin/vpn_config_pending_delete_form.html"
    assert response.context["eligible_count"] == 2
    assert len(response.context["configs"]) == 3
    assert response.context["pks"] == "1,2,3"


@pytest.mark.asyncio
async def test_mark_pending_delete_with_preset_reason(admin, monkeypatch):
    """Выбор пресета передаёт его текст как причину в DAO."""
    configs = [make_config(1, VPNConfigStatus.ACTIVE)]
    patch_async_session(monkeypatch, configs)
    mock_mark = AsyncMock(return_value=1)
    monkeypatch.setattr(VPNConfigDAO, "mark_pending_delete", mock_mark)

    request = make_request(
        form={"pks": "1", "reason_preset": "Истекла подписка", "reason_custom": ""}
    )

    response = await admin.mark_pending_delete(request)

    mock_mark.assert_awaited_once()
    call_kwargs = mock_mark.call_args.kwargs
    assert call_kwargs["config_ids"] == [1]
    assert call_kwargs["reason"] == "Истекла подписка"
    assert response.template == "admin/vpn_config_pending_delete_done.html"
    assert response.context["updated_count"] == 1
    assert response.context["reason"] == "Истекла подписка"


@pytest.mark.asyncio
async def test_mark_pending_delete_with_custom_reason(admin, monkeypatch):
    """Пресет "Другое" берёт текст из свободного поля, а не из названия пресета."""
    configs = [make_config(1, VPNConfigStatus.ACTIVE)]
    patch_async_session(monkeypatch, configs)
    mock_mark = AsyncMock(return_value=1)
    monkeypatch.setattr(VPNConfigDAO, "mark_pending_delete", mock_mark)

    request = make_request(
        form={
            "pks": "1",
            "reason_preset": "Другое",
            "reason_custom": "Переезд на новую ноду fi-02",
        }
    )

    await admin.mark_pending_delete(request)

    call_kwargs = mock_mark.call_args.kwargs
    assert call_kwargs["reason"] == "Переезд на новую ноду fi-02"


@pytest.mark.asyncio
async def test_mark_pending_delete_empty_reason_rerenders_form(admin, monkeypatch):
    """Пресет "Другое" без текста причины не бьёт по БД — форма с ошибкой."""
    configs = [make_config(1, VPNConfigStatus.ACTIVE)]
    patch_async_session(monkeypatch, configs)
    mock_mark = AsyncMock()
    monkeypatch.setattr(VPNConfigDAO, "mark_pending_delete", mock_mark)

    request = make_request(
        form={"pks": "1", "reason_preset": "Другое", "reason_custom": "   "}
    )

    response = await admin.mark_pending_delete(request)

    mock_mark.assert_not_awaited()
    assert response.template == "admin/vpn_config_pending_delete_form.html"
    assert "причину" in response.context["error"]


@pytest.mark.asyncio
async def test_parse_pks_ignores_blank_and_non_numeric_tokens():
    from api.vpn.admin import _parse_pks

    assert _parse_pks("1,2,3") == [1, 2, 3]
    assert _parse_pks("") == []
    assert _parse_pks("1,,abc,2") == [1, 2]
