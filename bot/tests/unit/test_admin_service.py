from unittest.mock import AsyncMock

import pytest

from bot.admin.enums import AdminModeKeys
from bot.admin.schemas import SYearIncome
from bot.admin.services import AdminService
from bot.users.schemas import SVPNConfigOut
from shared.enums.admin_enum import RoleEnum


@pytest.mark.asyncio
async def test_get_user_by_telegram_id(mock_admin_adapter, user_out):
    mock_admin_adapter.get_user_by_telegram_id.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.get_user_by_telegram_id(123456)

    mock_admin_adapter.get_user_by_telegram_id.assert_awaited_once_with(123456)
    assert user.telegram_id == 123456
    assert user.username == "test_user"


@pytest.mark.asyncio
async def test_get_users_by_filter(mock_admin_adapter, user_out):
    mock_admin_adapter.get_users.return_value = [user_out, user_out]
    service = AdminService(adapter=mock_admin_adapter)

    users = await service.get_users_by_filter(RoleEnum.USER)

    mock_admin_adapter.get_users.assert_awaited_once_with(RoleEnum.USER)
    assert len(users) == 2
    assert all(u.telegram_id == 123456 for u in users)


@pytest.mark.asyncio
async def test_change_user_role(mock_admin_adapter, user_out):
    mock_admin_adapter.change_user_role.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.change_user_role(123456, RoleEnum.ADMIN)

    mock_admin_adapter.change_user_role.assert_awaited_once()
    called_payload = mock_admin_adapter.change_user_role.call_args[0][0]
    assert called_payload.telegram_id == 123456
    assert called_payload.role_name == RoleEnum.ADMIN
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_extend_user_subscription(mock_admin_adapter, user_out):
    mock_admin_adapter.extend_subscription.return_value = user_out
    service = AdminService(adapter=mock_admin_adapter)

    user = await service.extend_user_subscription(123456, 3)

    mock_admin_adapter.extend_subscription.assert_awaited_once()
    called_payload = mock_admin_adapter.extend_subscription.call_args[0][0]
    assert called_payload.telegram_id == 123456
    assert called_payload.months == 3
    assert user.telegram_id == 123456


@pytest.mark.asyncio
async def test_format_user_text_full_info(user_out):
    """Полностью заполненный пользователь — все поля и список конфигов рендерятся."""
    user = user_out.model_copy(
        update={
            "vpn_configs": [
                SVPNConfigOut(id=1, file_name="conf1.conf", pub_key="PUBKEY1"),
                SVPNConfigOut(id=2, file_name="conf2.conf", pub_key="PUBKEY2"),
            ]
        }
    )

    text = await AdminService.format_user_text(user)

    assert "John" in text
    assert "Doe" in text
    assert "@test_user" in text
    assert "123456" in text
    assert "📌 conf1.conf" in text
    assert "📌 conf2.conf" in text


@pytest.mark.asyncio
async def test_format_user_text_missing_fields_fallback_to_dash(user_out):
    """Отсутствующие first_name/last_name/username подставляются как "-", а не None/пусто."""
    user = user_out.model_copy(
        update={"first_name": None, "last_name": None, "username": None}
    )

    text = await AdminService.format_user_text(user)

    assert "<b>Имя:</b> - -" in text
    assert "@-" in text


@pytest.mark.asyncio
async def test_format_user_text_no_vpn_configs_omits_config_block(user_out):
    """Пустой список конфигов — блок "Пользовательские конфиги" не выводится вовсе."""
    assert user_out.vpn_configs == []

    text = await AdminService.format_user_text(user_out)

    assert "Пользовательские конфиги" not in text


@pytest.mark.asyncio
async def test_format_user_text_no_subscription_shows_dash(user_out):
    """Нет активной подписки — "-" вместо строкового представления подписки."""
    user = user_out.model_copy(update={"current_subscription": None})

    text = await AdminService.format_user_text(user)

    assert "💎 <b>Подписка:</b> -" in text


@pytest.mark.asyncio
async def test_format_user_text_edit_user_key_uses_edit_template(user_out):
    """key=EDIT_USER рендерит другой шаблон (заголовок редактирования), не "user"."""
    text = await AdminService.format_user_text(user_out, key=AdminModeKeys.EDIT_USER)

    assert "Редактирование данных пользователя" in text


@pytest.mark.asyncio
async def test_year_income_calls_adapter(mocker):
    """Проверяет вызов adapter.year_income."""
    expected = SYearIncome(year_income=1000)

    adapter = mocker.Mock()
    adapter.year_income = AsyncMock(return_value=expected)

    service = AdminService(adapter)

    await service.year_income()

    adapter.year_income.assert_awaited_once()


@pytest.mark.asyncio
async def test_year_income_returns_result(mocker):
    """Проверяет возврат результата адаптера."""
    expected = SYearIncome(year_income=1000)

    adapter = mocker.Mock()
    adapter.year_income = AsyncMock(return_value=expected)

    service = AdminService(adapter)

    result = await service.year_income()

    assert result == expected
    assert result.year_income == 1000
