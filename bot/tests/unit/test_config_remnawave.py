from uuid import uuid4

import pytest
from pydantic import ValidationError

from bot.core.config import REMNAWAVE_SUBSCRIPTION_TIERS, RemnawaveSettings

pytestmark = pytest.mark.vpn


def _valid_kwargs() -> dict:
    """Корректный набор полей секции remnawave (все тиры замаплены, squads непустые)."""
    squads = {"standard": [uuid4()], "premium": [uuid4()]}
    tier_map = {t: "standard" for t in REMNAWAVE_SUBSCRIPTION_TIERS}
    return {
        "api_url": "h",
        "squads": squads,
        "tier_map": tier_map,
        "token": "secret",
    }


@pytest.mark.asyncio
async def test_valid_section_constructs_with_enabled_false_by_default():
    """Все SubscriptionType замаплены и squads непустые -> объект создаётся, enabled=False по умолчанию."""
    settings = RemnawaveSettings(**_valid_kwargs())

    assert settings.enabled is False


@pytest.mark.asyncio
async def test_tier_map_missing_subscription_type_raises():
    """В tier_map не хватает какого-то типа подписки -> ValidationError."""
    kwargs = _valid_kwargs()
    kwargs["tier_map"] = {
        t: "standard" for t in REMNAWAVE_SUBSCRIPTION_TIERS if t != "premium"
    }

    with pytest.raises(ValidationError):
        RemnawaveSettings(**kwargs)


@pytest.mark.asyncio
async def test_tier_map_points_to_missing_squad_key_raises():
    """tier_map ссылается на ключ, которого нет в squads -> ValidationError."""
    kwargs = _valid_kwargs()
    kwargs["tier_map"] = {t: "ghost_group" for t in REMNAWAVE_SUBSCRIPTION_TIERS}

    with pytest.raises(ValidationError):
        RemnawaveSettings(**kwargs)


@pytest.mark.asyncio
async def test_squads_with_empty_list_raises():
    """В squads есть пустой список -> ValidationError."""
    kwargs = _valid_kwargs()
    kwargs["squads"] = {"standard": [], "premium": [uuid4()]}

    with pytest.raises(ValidationError):
        RemnawaveSettings(**kwargs)


@pytest.mark.asyncio
async def test_enabled_true_with_empty_token_raises():
    """enabled=True, token='' -> ValidationError."""
    kwargs = _valid_kwargs()
    kwargs["token"] = ""
    kwargs["enabled"] = True

    with pytest.raises(ValidationError):
        RemnawaveSettings(**kwargs)


def test_tiers_match_subscription_type_enum():
    """REMNAWAVE_SUBSCRIPTION_TIERS совпадает со значениями SubscriptionType -> ручной дубликат не разъехался."""
    # bot/ не импортирует api/ в рантайме (только через APIClient); здесь это
    # тест-only guard на синхронизацию ручного дубликата из bot/core/config.py
    # со значениями SubscriptionType — см. TODO в плане Remnawave.
    from api.subscription.models import SubscriptionType

    assert set(REMNAWAVE_SUBSCRIPTION_TIERS) == {t.value for t in SubscriptionType}
