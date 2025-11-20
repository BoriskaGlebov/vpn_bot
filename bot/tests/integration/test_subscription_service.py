from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from loguru import logger as real_logger

from bot.subscription.models import SubscriptionType
from bot.subscription.services import SubscriptionService
from bot.users.models import User


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_check_premium_active(test_bot: Bot, setup_users, session):
    """Проверка, что премиум-подписка определяется корректно."""
    svc = SubscriptionService(bot=test_bot, logger=real_logger)

    user = setup_users[0]  # Admin, premium
    premium, role, active = await svc.check_premium(
        session=session, tg_id=user.telegram_id
    )

    assert premium is True
    assert role == user.role.name
    assert active is False


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_check_premium_standard(test_bot: Bot, setup_users, session):
    """Проверка обычной подписки."""
    svc = SubscriptionService(bot=test_bot, logger=real_logger)

    user = setup_users[2]  # обычный user, STANDARD
    premium, role, active = await svc.check_premium(
        session=session, tg_id=user.telegram_id
    )

    assert premium is False
    assert role == user.role.name
    assert active is False


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_start_trial_subscription_creates_trial(
    test_bot: Bot, setup_users, session
):
    """Тест активации пробного периода для нового пользователя."""
    svc = SubscriptionService(bot=test_bot, logger=real_logger)
    user = setup_users[2]  # обычный user

    # Делаем подписку неактивной, чтобы имитировать старт trial
    user.subscription.is_active = False
    user.has_used_trial = False
    await session.commit()

    await svc.start_trial_subscription(
        session=session, user_id=user.telegram_id, days=7
    )

    updated_user = await session.get(User, user.id)
    assert updated_user.subscription.type == SubscriptionType.TRIAL
    assert updated_user.subscription.is_active is True
    assert updated_user.has_used_trial is True


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_activate_paid_subscription_upgrade(test_bot: Bot, setup_users, session):
    """Тест активации платной подписки и апгрейда подписки."""
    svc = SubscriptionService(bot=test_bot, logger=real_logger)
    user = setup_users[2]  # обычный user, STANDARD

    result = await svc.activate_paid_subscription(
        session=session, user_id=user.telegram_id, months=1, premium=True
    )
    assert result.subscription.type == SubscriptionType.PREMIUM


@pytest.mark.asyncio
@pytest.mark.subscription
async def test_check_all_subscriptions_notifications(
    test_bot: Bot, setup_users, session, monkeypatch
):
    """Тест проверки всех подписок и отправки уведомлений."""
    svc = SubscriptionService(bot=test_bot, logger=real_logger)
    user = setup_users[2]  # обычный user

    # Устанавливаем подписку так, чтобы осталось 2 дня
    user.subscription.end_date = datetime.now(tz=UTC) + timedelta(days=2)
    await session.commit()

    # Мокируем отправку сообщений, чтобы не летели реально
    monkeypatch.setattr(test_bot, "send_message", AsyncMock())

    stats = await svc.check_all_subscriptions(session=session)
    assert stats["checked"] == len(setup_users)
    assert stats["notified"] == 0
