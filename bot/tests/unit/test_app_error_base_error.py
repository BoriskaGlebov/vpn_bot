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

    assert str(err) == "[app_error] base error"


def test_app_error_str_with_cause():
    cause = ValueError("boom")
    err = AppError("wrapped", cause=cause)

    assert str(err) == "[app_error] wrapped"
    assert err.cause is cause


# =========================
# UserNotFoundError
# =========================


def test_user_not_found_error():
    tg_id = 12345
    err = UserNotFoundError(tg_id)

    assert err.tg_id == tg_id
    assert str(err) == f"[user_not_found] Пользователь с Telegram ID {tg_id} не найден"


# =========================
# SubscriptionNotFoundError
# =========================


def test_subscription_not_found_error():
    tg_id = 42
    err = SubscriptionNotFoundError(tg_id)

    assert err.tg_id == tg_id
    assert (
        str(err)
        == f"[subscription_not_found] У пользователя {tg_id} нет активной подписки"
    )


# =========================
# VPNLimitError
# =========================


@pytest.mark.parametrize(
    ("tg_id", "limit", "current", "username"),
    [
        (1, 3, 3, "john"),
        (2, 5, 4, ""),
    ],
)
def test_vpn_limit_error(tg_id, limit, current, username):
    err = VPNLimitError(tg_id=tg_id, limit=limit, current=current, username=username)

    assert err.tg_id == tg_id
    assert err.limit == limit
    assert err.current == current
    assert err.username == username
    assert str(err) == (
        f"[vpn_limit_reached] Пользователь достиг лимита "
        f"VPN-конфигов ({current}/{limit})"
    )
    assert err.details == {
        "tg_id": tg_id,
        "limit": limit,
        "current": current,
        "username": username,
    }
