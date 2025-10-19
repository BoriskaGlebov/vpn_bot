from unittest.mock import AsyncMock, patch

import pytest

from bot.users.dao import RoleDAO
from bot.users.schemas import SRole
from bot.utils.init_default_roles import init_default_roles


@pytest.mark.asyncio
@pytest.mark.utils
async def test_init_default_roles_adds_missing_roles():
    existing_roles = [SRole(name="admin", description="Администратор")]
    with (
        patch.object(RoleDAO, "find_all", new_callable=AsyncMock) as mock_find_all,
        patch.object(RoleDAO, "add", new_callable=AsyncMock) as mock_add,
    ):

        mock_find_all.return_value = existing_roles

        await init_default_roles()

        # Проверяем, что add вызвался только для ролей, которых нет в БД
        expected_calls = [
            # Сначала была "founder", потом "user"
            SRole(name="founder", description="Пользователи с правами основателя"),
            SRole(name="user", description="Обычный пользователь"),
        ]
        actual_calls = [call.args[1] for call in mock_add.await_args_list]
        for expected, actual in zip(expected_calls, actual_calls):
            assert expected.name == actual.name
            assert expected.description == actual.description

        # find_all вызвался ровно один раз
        mock_find_all.assert_awaited_once()
