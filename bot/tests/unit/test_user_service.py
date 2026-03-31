from unittest.mock import AsyncMock

import pytest
from users.schemas import SUserOut

from bot.users.adapter import UsersAPIAdapter
from bot.users.services import UserService


@pytest.fixture
def users_adapter_mock():
    return AsyncMock(spec=UsersAPIAdapter)


@pytest.mark.asyncio
async def test_register_new_user(users_adapter_mock, tg_user, user_out):
    users_adapter_mock.register.return_value = (user_out, True)

    service = UserService(users_adapter_mock)

    result, is_new = await service.register_or_get_user(tg_user)

    # ✔ проверяем результат
    assert isinstance(result, SUserOut)
    assert is_new is True

    # ✔ проверяем что адаптер вызвался правильно
    users_adapter_mock.register.assert_awaited_once()

    called_arg = users_adapter_mock.register.call_args[0][0]

    assert called_arg.telegram_id == tg_user.id
    assert called_arg.username == tg_user.username


@pytest.mark.asyncio
async def test_register_existing_user(users_adapter_mock, tg_user, user_out):
    users_adapter_mock.register.return_value = (user_out, False)

    service = UserService(users_adapter_mock)

    result, is_new = await service.register_or_get_user(tg_user)

    assert result.id == user_out.id
    assert is_new is False


@pytest.mark.asyncio
async def test_username_fallback(users_adapter_mock, user_out):
    tg_user = type(
        "TgUser",
        (),
        {
            "id": 999,
            "username": None,
            "first_name": "NoName",
            "last_name": None,
        },
    )()

    users_adapter_mock.register.return_value = (user_out, True)

    service = UserService(users_adapter_mock)

    await service.register_or_get_user(tg_user)

    called_arg = users_adapter_mock.register.call_args[0][0]

    assert called_arg.username == "Гость_999"
