"""#277: выдача TRIAL через форму подписки обходила has_used_trial."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from api.app_error.base_error import TrialAlreadyUsedError
from api.subscription.admin import SubscriptionAdmin
from api.subscription.models import SubscriptionType


@pytest.fixture
def admin():
    return SubscriptionAdmin()


@pytest.mark.asyncio
async def test_non_trial_type_skips_check(admin):
    """Любой тип кроме TRIAL — проверка не выполняется вовсе."""
    model = MagicMock(user=None)

    await admin.on_model_change(
        {"type": SubscriptionType.STANDARD.name},
        model,
        is_created=True,
        request=MagicMock(),
    )


@pytest.mark.asyncio
async def test_trial_blocked_when_user_already_used_it(admin):
    """Редактирование существующей подписки: model.user уже загружен
    (selectinload формы) и has_used_trial=True -> запрещено.
    """
    user = MagicMock(id=1, username="test", has_used_trial=True)
    model = MagicMock(user=user)

    with pytest.raises(TrialAlreadyUsedError):
        await admin.on_model_change(
            {"type": SubscriptionType.TRIAL.name},
            model,
            is_created=False,
            request=MagicMock(),
        )


@pytest.mark.asyncio
async def test_trial_allowed_when_user_has_not_used_it(admin):
    """has_used_trial=False -> форма сохраняется, ошибки нет."""
    user = MagicMock(id=1, username="test", has_used_trial=False)
    model = MagicMock(user=user)

    await admin.on_model_change(
        {"type": SubscriptionType.TRIAL.name},
        model,
        is_created=False,
        request=MagicMock(),
    )


@pytest.mark.asyncio
async def test_trial_create_resolves_user_by_submitted_pk(admin, monkeypatch):
    """Создание новой записи: model.user ещё не выставлен — пользователь
    определяется запросом по pk, присланному формой (QuerySelectField).
    """
    found_user = MagicMock(id=42, username="created", has_used_trial=True)
    session = AsyncMock()
    session.get = AsyncMock(return_value=found_user)
    session_cm = AsyncMock()
    session_cm.__aenter__.return_value = session
    session_cm.__aexit__.return_value = False
    monkeypatch.setattr(admin, "session_maker", MagicMock(return_value=session_cm))

    with pytest.raises(TrialAlreadyUsedError):
        await admin.on_model_change(
            {"type": SubscriptionType.TRIAL.name, "user": "42"},
            MagicMock(user=None),
            is_created=True,
            request=MagicMock(),
        )

    session.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_trial_create_without_resolvable_user_skips_silently(admin):
    """Непарсимый pk пользователя (data['user'] не int-строка) — проверка
    пропускается, а не роняет форму 500-й ошибкой.
    """
    await admin.on_model_change(
        {"type": SubscriptionType.TRIAL.name, "user": "not-a-pk"},
        MagicMock(user=None),
        is_created=True,
        request=MagicMock(),
    )
