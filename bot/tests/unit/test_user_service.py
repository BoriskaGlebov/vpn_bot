from typing import Any
from unittest.mock import AsyncMock

import pytest

from bot.users.adapter import UsersAPIAdapter
from bot.users.schemas import SUserOut
from bot.users.services import UserService


@pytest.fixture
def users_adapter_mock() -> AsyncMock:
    """Фикстура мока адаптера пользователей.

    Возвращает:
        AsyncMock: мок с интерфейсом UsersAPIAdapter.
    """
    return AsyncMock(spec=UsersAPIAdapter)


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_register_new_user(
    users_adapter_mock: AsyncMock,
    tg_user: Any,
    user_out: SUserOut,
) -> None:
    """Проверяет регистрацию нового пользователя в сервисе.

    Сценарий:
        - адаптер возвращает (user, True);
        - пользователь считается новым.

    Проверяется:
        - корректный возврат результата;
        - флаг is_new == True;
        - корректный вызов адаптера с SUser.
    """
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
async def test_register_existing_user(
    users_adapter_mock: AsyncMock,
    tg_user: Any,
    user_out: SUserOut,
) -> None:
    """Проверяет сценарий существующего пользователя.

    Сценарий:
        - адаптер возвращает (user, False).

    Проверяется:
        - корректный возврат пользователя;
        - флаг is_new == False.
    """

    users_adapter_mock.register.return_value = (user_out, False)

    service = UserService(users_adapter_mock)

    result, is_new = await service.register_or_get_user(tg_user)

    assert result.id == user_out.id
    assert is_new is False


@pytest.mark.asyncio
async def test_username_fallback(
    users_adapter_mock: AsyncMock,
    user_out: SUserOut,
) -> None:
    """Проверяет fallback для username.

    Сценарий:
        - у Telegram пользователя отсутствует username;
        - сервис должен сгенерировать значение вида "Гость_<id>".

    Проверяется:
        - корректная генерация username;
        - передача значения в адаптер.
    """
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
