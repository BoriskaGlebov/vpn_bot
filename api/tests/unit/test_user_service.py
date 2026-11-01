from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import UserNotFoundError
from api.subscription.models import SubscriptionType
from api.users.schemas import (
    SUser,
    SUserOut,
    SUserWithReferralStats,
)
from api.users.services import UserService

pytestmark = pytest.mark.asyncio


@pytest.fixture
def service() -> UserService:
    return UserService()


@pytest.fixture
def session() -> AsyncSession:
    return MagicMock(spec=AsyncSession)


# ---------- register_or_get_user ----------


@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_existing(
    mock_find_user,
    mock_to_schema,
    service,
    session,
):
    """Пользователь уже существует -> возвращается без создания, created=False."""
    fake_user = MagicMock(username="existing_user", first_name="Test", last_name="User")
    mock_find_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserOut)
    mock_to_schema.return_value = expected_schema

    telegram_user = SUser(
        telegram_id=123,
        username="existing_user",
        first_name="Test",
        last_name="User",
    )

    result, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert result is expected_schema
    assert created is False

    mock_find_user.assert_awaited_once()
    mock_to_schema.assert_called_once_with(fake_user)


@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.patch", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_updates_changed_username(
    mock_find_user,
    mock_patch,
    mock_to_schema,
    service,
    session,
):
    """Существующий пользователь прислал новый непустой username -> обновляем."""
    fake_user = MagicMock(username="old_name", first_name=None, last_name=None)
    mock_find_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(telegram_id=123, username="new_name")

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    mock_patch.assert_awaited_once()
    _, kwargs = mock_patch.await_args
    assert kwargs["values"].username == "new_name"


@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.patch", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_updates_changed_first_and_last_name(
    mock_find_user,
    mock_patch,
    mock_to_schema,
    service,
    session,
):
    """Существующий пользователь прислал новые first_name/last_name -> обновляем.

    username при этом не меняется — в SET должно попасть текущее значение
    из БД, а не None (все три поля всегда передаются явно в SProfileUpdate).
    """
    fake_user = MagicMock(
        username="same_name", first_name="OldFirst", last_name="OldLast"
    )
    mock_find_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=123,
        username="same_name",
        first_name="NewFirst",
        last_name="NewLast",
    )

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    mock_patch.assert_awaited_once()
    _, kwargs = mock_patch.await_args
    assert kwargs["values"].username == "same_name"
    assert kwargs["values"].first_name == "NewFirst"
    assert kwargs["values"].last_name == "NewLast"


@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.update", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_empty_first_last_name_does_not_clear_existing(
    mock_find_user,
    mock_update,
    mock_to_schema,
    service,
    session,
):
    """Входящие first_name/last_name=None НЕ затирают сохранённые значения.

    Те же вызовы без полного профиля, что защищены для username (bot/vpn/
    services.py, bot/core/filters.py), не должны затирать имя/фамилию.
    """
    fake_user = MagicMock(
        username="real_username", first_name="RealFirst", last_name="RealLast"
    )
    mock_find_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=123, username=None, first_name=None, last_name=None
    )

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    mock_update.assert_not_awaited()


@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.update", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_empty_username_does_not_clear_existing(
    mock_find_user,
    mock_update,
    mock_to_schema,
    service,
    session,
):
    """Входящий username=None НЕ затирает сохранённый username (регрессия).

    Часть вызовов `/users/register` (например, проверка лимита конфигов в
    bot/vpn/services.py, фильтр IsPremium в bot/core/filters.py — до их
    собственного фикса) передают только telegram_id, без профиля, и
    `SUser.model_dump()` сериализует отсутствующий username как `null` в
    JSON-теле. Без этой проверки такой вызов читался как "пользователь стёр
    username в Telegram" и затирал реальное значение.
    """
    fake_user = MagicMock(username="real_username")
    mock_find_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(telegram_id=123, username=None)

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    mock_update.assert_not_awaited()


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_create_admin(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Создание администратора."""
    mock_find_user.return_value = None
    mock_settings.core.admin_ids = [999]

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserOut)
    mock_to_schema.return_value = expected_schema

    telegram_user = SUser(
        telegram_id=999,
        username="admin_user",
        first_name="Admin",
        last_name="User",
    )

    result, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert created is True
    assert result == expected_schema

    # Проверяем, что была назначена роль admin
    args, kwargs = mock_add_user.await_args
    assert kwargs["values_role"].name == "admin"
    # «admin -> бессрочный премиум» — решает сервис явными параметрами,
    # не DAO по имени роли (#244).
    assert kwargs["subscription_is_active"] is True
    assert kwargs["subscription_type"] == SubscriptionType.PREMIUM


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_create_regular_user(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Создание обычного пользователя."""
    mock_find_user.return_value = None
    mock_settings.admin_ids = []

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=123,
        username="regular_user",
        first_name="Test",
        last_name="User",
    )

    _, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert created is True

    args, kwargs = mock_add_user.await_args
    assert kwargs["values_role"].name == "user"
    assert kwargs["subscription_is_active"] is False
    assert kwargs["subscription_type"] is None


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_guest_username(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Если username отсутствует, передаётся как None, а не подставляется (#242):
    username переиспользуем, подстановка "Гость_<id>" заняла бы NULL навечно.
    """
    mock_find_user.return_value = None
    mock_settings.admin_ids = []

    fake_user = MagicMock()
    mock_add_user.return_value = fake_user
    mock_to_schema.return_value = MagicMock(spec=SUserOut)

    telegram_user = SUser(
        telegram_id=555,
        username=None,
        first_name="Guest",
        last_name="User",
    )

    await service.register_or_get_user(session=session, telegram_user=telegram_user)

    args, kwargs = mock_add_user.await_args
    assert kwargs["values_user"].username is None


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_concurrent_registration_race(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """Гонка (#239): INSERT падает на unique(telegram_id) — другой запрос уже
    создал пользователя между нашим SELECT и INSERT. Ожидается не 500, а
    существующий пользователь с created=False, после повторного чтения.
    """
    mock_settings.core.admin_ids = []
    existing_user = MagicMock()
    # Первый find_one_or_none (до попытки создания) не находит пользователя;
    # второй (после отловленного IntegrityError) находит запись, которую
    # успел создать параллельный запрос.
    mock_find_user.side_effect = [None, existing_user]
    mock_add_user.side_effect = IntegrityError("INSERT", {}, Exception("unique"))

    expected_schema = MagicMock(spec=SUserOut)
    mock_to_schema.return_value = expected_schema

    telegram_user = SUser(
        telegram_id=123,
        username="racer",
        first_name="Test",
        last_name="User",
    )

    result, created = await service.register_or_get_user(
        session=session,
        telegram_user=telegram_user,
    )

    assert created is False
    assert result is expected_schema
    assert mock_find_user.await_count == 2
    mock_to_schema.assert_called_once_with(existing_user)


@patch("api.users.services.settings_api")
@patch("api.users.services.UserMapper.to_schema", new_callable=MagicMock)
@patch("api.users.services.UserDAO.add_role_subscription", new_callable=AsyncMock)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_register_or_get_user_race_without_visible_row_reraises(
    mock_find_user,
    mock_add_user,
    mock_to_schema,
    mock_settings,
    service,
    session,
):
    """IntegrityError, которую не объясняет повторное чтение (не telegram_id,
    либо строка конкурента ещё не закоммитилась), должна дойти до вызывающего
    — а не быть замаскирована под «пользователь не найден».
    """
    mock_settings.core.admin_ids = []
    mock_find_user.side_effect = [None, None]
    mock_add_user.side_effect = IntegrityError("INSERT", {}, Exception("unique"))

    telegram_user = SUser(
        telegram_id=123,
        username="racer",
        first_name="Test",
        last_name="User",
    )

    with pytest.raises(IntegrityError):
        await service.register_or_get_user(
            session=session,
            telegram_user=telegram_user,
        )

    mock_to_schema.assert_not_called()


# ---------- get_user_with_referrals ----------


@patch(
    "api.users.services.UserMapper.to_schema_with_referrals",
    new_callable=MagicMock,
)
@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_get_user_with_referrals_found(
    mock_find_user,
    mock_to_schema,
    service,
    session,
):
    """Пользователь найден."""
    fake_user = MagicMock()
    mock_find_user.return_value = fake_user

    expected_schema = MagicMock(spec=SUserWithReferralStats)
    mock_to_schema.return_value = expected_schema

    result = await service.get_user_with_referrals(
        session=session,
        telegram_id=123,
    )

    assert result == expected_schema
    mock_to_schema.assert_called_once_with(fake_user)


@patch("api.users.services.UserDAO.find_one_or_none", new_callable=AsyncMock)
async def test_get_user_with_referrals_not_found(
    mock_find_user,
    service,
    session,
):
    """Пользователь не найден -> UserNotFoundError (404)."""
    mock_find_user.return_value = None

    with pytest.raises(UserNotFoundError) as exc_info:
        await service.get_user_with_referrals(
            session=session,
            telegram_id=123,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "user_not_found"
