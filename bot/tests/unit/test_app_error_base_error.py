import pytest

from bot.app_error.base_error import (
    AppError,
    SubscriptionNotFoundError,
    UserNotFoundError,
    VPNLimitError,
)

# =========================
# AppError
# =========================


def test_app_error_str_without_cause():
    err = AppError("base error")

    assert str(err) == "base error"


def test_app_error_str_with_cause():
    cause = ValueError("boom")
    err = AppError("wrapped", cause=cause)

    assert str(err) == "wrapped (cause: boom)"
    assert err.cause is cause


# =========================
# UserNotFoundError
# =========================


def test_user_not_found_error():
    tg_id = 12345
    err = UserNotFoundError(tg_id)

    assert err.tg_id == tg_id
    assert str(err) == f"Пользователь с Telegram ID {tg_id} не найден."


# =========================
# SubscriptionNotFoundError
# =========================


def test_subscription_not_found_error():
    user_id = 42
    err = SubscriptionNotFoundError(user_id)

    assert err.user_id == user_id
    assert str(err) == f"У пользователя {user_id} нет подписки / не активна."


# =========================
# VPNLimitError
# =========================


@pytest.mark.parametrize(
    ("user_id", "limit", "username", "expected_message"),
    [
        (
            1,
            3,
            "john",
            "Пользователь 1 достиг лимита (3) конфигов.\n@john",
        ),
        (
            2,
            5,
            "",
            "Пользователь 2 достиг лимита (5) конфигов.\n",
        ),
    ],
)
def test_vpn_limit_error(user_id, limit, username, expected_message):
    err = VPNLimitError(user_id, limit, username)

    assert err.user_id == user_id
    assert err.limit == limit
    assert err.username == username
    assert str(err) == expected_message
