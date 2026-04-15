from unittest.mock import AsyncMock

import pytest

from bot.utils.set_description_file import set_description


@pytest.mark.asyncio
@pytest.mark.utils
async def test_set_description_calls_methods(
    fake_bot: AsyncMock,
    patch_deps,
) -> None:
    """Проверяет, что устанавливается описание бота.

    Кейс:
    - вызывается get_me (бот доступен)
    - вызывается set_my_description с текстом из настроек
    """

    # act
    await set_description(fake_bot)

    # assert
    fake_bot.get_me.assert_awaited_once()

    fake_bot.set_my_description.assert_awaited_once_with(
        description="Описание работы Бота"
    )
