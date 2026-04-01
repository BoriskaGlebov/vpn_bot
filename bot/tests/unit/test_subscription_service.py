from unittest.mock import AsyncMock

import pytest

from bot.subscription.schemas import SSubscriptionCheck
from bot.subscription.services import SubscriptionService
from bot.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum
from shared.enums.subscription_enum import TrialStatus


@pytest.fixture
def adapter_mock():
    return AsyncMock()


@pytest.fixture
def service(adapter_mock):
    return SubscriptionService(adapter_mock)


@pytest.mark.asyncio
async def test_check_premium(service, adapter_mock):
    adapter_mock.check_premium.return_value = SSubscriptionCheck(
        premium=True,
        role=RoleEnum.USER,
        is_active=True,
    )

    result = await service.check_premium(tg_id=123)

    assert result == (True, RoleEnum.USER, True)

    adapter_mock.check_premium.assert_awaited_once_with(tg_id=123)


@pytest.mark.asyncio
async def test_start_trial_subscription(service, adapter_mock):
    adapter_mock.activate_trial.return_value = (
        {"status": TrialStatus.STARTED},
        201,
    )

    await service.start_trial_subscription(tg_id=123, days=7)

    adapter_mock.activate_trial.assert_awaited_once_with(
        tg_id=123,
        days=7,
    )


from unittest.mock import AsyncMock

import pytest
from pydantic import parse_obj_as

from bot.subscription.services import SubscriptionService
from bot.users.schemas import SUserOut


@pytest.mark.asyncio
async def test_activate_paid_subscription(service, adapter_mock, user_out):
    adapter_mock.activate_paid.return_value = user_out.model_dump()

    result = await service.activate_paid_subscription(
        tg_id=user_out.telegram_id,
        months=3,
        premium=True,
    )

    result = SUserOut.model_validate(result)

    assert result.model_dump() == user_out.model_dump()

    adapter_mock.activate_paid.assert_awaited_once_with(
        tg_id=user_out.telegram_id,
        months=3,
        premium=True,
    )
