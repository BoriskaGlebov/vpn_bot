from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import CallbackQuery, Message

from bot.app_error.schema import ErrorDetail, ErrorEnvelope
from bot.core.config import settings_bot
from bot.middleware.exception_middleware import ErrorHandlerMiddleware
from bot.middleware.user_action_middleware import UserActionLoggingMiddleware


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_handles_message_exception(monkeypatch, fake_logger, fake_bot):
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    exc = TelegramBadRequest(method=MagicMock(), message="invalid request")

    async def fake_handler(event, data):
        raise exc

    # Мокаем Message и from_user
    fake_from_user = MagicMock()
    fake_from_user.id = 123

    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_from_user
    fake_message.reply = AsyncMock()
    await mw(fake_handler, fake_message, {})
    fake_message.reply.assert_awaited_once()
    sent_text = fake_message.reply.call_args[0][0]

    expected_text = mw._resolve_user_message(mw._normalize_exception(exc))
    assert sent_text == expected_text


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_handles_callback_query_exception(
    monkeypatch, fake_logger, fake_bot
):
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    exc = TelegramRetryAfter(
        method=MagicMock(), message="Too Many Requests", retry_after=10
    )

    async def fake_handler(event, data):
        raise exc

    fake_from_user = MagicMock()
    fake_from_user.id = 456

    fake_message = MagicMock()
    fake_message.answer = AsyncMock()

    fake_query = MagicMock(spec=CallbackQuery)
    fake_query.from_user = fake_from_user
    fake_query.message = fake_message
    await mw(fake_handler, fake_query, {})

    fake_message.answer.assert_awaited_once()
    sent_text = fake_message.answer.call_args[0][0]

    expected_text = mw._resolve_user_message(mw._normalize_exception(exc))
    assert sent_text == expected_text


@pytest.mark.middleware
def test_resolve_user_message_unknown_code_returns_generic_text(fake_logger, fake_bot):
    """Неизвестный код ошибки даёт общий текст, а не message дословно (#241).

    Раньше case _ отдавал message как есть — любой непредусмотренный код
    (включая технический, вроде репра исключения) становился видимым в чате.
    """
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="some_brand_new_code_nobody_reviewed_yet",
            message="RequestValidationError([{'input': 'secret-value', ...}])",
        )
    )

    result = mw._resolve_user_message(envelope)

    assert result == settings_bot.messages.general.common_error
    assert "secret-value" not in result


@pytest.mark.middleware
def test_resolve_user_message_validation_error_code_returns_generic_text(
    fake_logger, fake_bot
):
    """validation_error (из api/, не входит в safe-список) не доходит до
    пользователя дословно — тот же сценарий, что чинит #240 на стороне api/,
    но проверяется здесь на уровне правила по умолчанию.
    """
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    envelope = ErrorEnvelope(
        error=ErrorDetail(code="validation_error", message="Ошибка валидации запроса")
    )

    result = mw._resolve_user_message(envelope)

    assert result == settings_bot.messages.general.common_error


@pytest.mark.parametrize(
    "code",
    [
        "user_not_found",
        "role_not_found",
        "subscription_error",
        "device_instruction_mismatch",
        "no_admin_configured",
    ],
)
@pytest.mark.middleware
def test_resolve_user_message_known_safe_code_passes_through(
    fake_logger, fake_bot, code
):
    """Коды из явного safe-списка (проверенные, написанные для пользователя)
    продолжают показываться как есть (#241).
    """
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    safe_text = "Заранее проверенный, человекочитаемый текст"
    envelope = ErrorEnvelope(error=ErrorDetail(code=code, message=safe_text))

    result = mw._resolve_user_message(envelope)

    assert result == safe_text


@pytest.mark.middleware
def test_resolve_user_message_telegram_bad_request_no_self_duplicate(
    fake_logger, fake_bot
):
    """#284: telegram_bad_request раньше подставлял свой же текст в шаблон
    f"⚠️ Неверный запрос: {message}", давая дубль в одной строке.
    """
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    envelope = ErrorEnvelope(
        error=ErrorDetail(code="telegram_bad_request", message="⚠️ Неверный запрос.")
    )

    result = mw._resolve_user_message(envelope)

    assert result == "⚠️ Неверный запрос."
    assert result.count("Неверный запрос") == 1


@pytest.mark.parametrize(
    "code",
    [
        "telegram_forbidden",
        "telegram_unauthorized",
        "telegram_not_found",
        "telegram_entity_too_large",
        "telegram_network_error",
        "telegram_server_error",
        "telegram_restarting",
        "telegram_migrate_to_chat",
        "telegram_conflict",
        "telegram_api_error",
    ],
)
@pytest.mark.middleware
def test_resolve_user_message_telegram_codes_now_reachable(fake_logger, fake_bot, code):
    """#284: эти десять кодов из telegram_map раньше попадали в case `_` и
    показывали общий текст ошибки вместо написанного для них сообщения.
    """
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    written_text = "⚠️ Заранее написанный текст для этого кода."
    envelope = ErrorEnvelope(error=ErrorDetail(code=code, message=written_text))

    result = mw._resolve_user_message(envelope)

    assert result == written_text
    assert result != settings_bot.messages.general.common_error


@pytest.mark.middleware
def test_resolve_user_message_vpn_limit_shows_current_not_limit_twice(
    fake_logger, fake_bot
):
    """#284: счётчик лимита показывал limit/limit вместо current/limit."""
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)
    envelope = ErrorEnvelope(
        error=ErrorDetail(
            code="vpn_limit_reached",
            message="Пользователь достиг лимита VPN-конфигов (2/5)",
            details={"tg_id": 1, "limit": 5, "current": 2, "username": "u"},
        )
    )

    result = mw._resolve_user_message(envelope)

    assert "2/5" in result


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_middleware_logs_exception(monkeypatch, fake_logger, fake_bot):
    mw = ErrorHandlerMiddleware(logger=fake_logger, bot=fake_bot)

    async def fake_handler(event, data):
        raise Exception("generic error")

    # Создаём from_user отдельно
    fake_from_user = MagicMock()
    fake_from_user.id = 789

    fake_message = MagicMock(spec=Message)
    fake_message.from_user = fake_from_user
    fake_message.reply = AsyncMock()

    await mw(fake_handler, fake_message, {})

    fake_message.reply.assert_awaited_once()
    fake_logger.bind.assert_called_with(user=789)
    fake_logger.bind().error.assert_called()


@pytest.mark.asyncio
@pytest.mark.middleware
async def test_user_action_logging_middleware(
    fake_logger, make_fake_message, monkeypatch
):
    """Проверяет, что UserActionLoggingMiddleware логирует START/END и вызывает handler."""

    # --- 1️⃣ Подготовка данных ---
    middleware = UserActionLoggingMiddleware(
        log_data=True, log_time=True, logger=fake_logger
    )
    fake_message = make_fake_message(user_id=123)
    data = {}

    # Фейковый обработчик
    fake_handler = AsyncMock(return_value="OK")

    # --- 2️⃣ Вызов middleware ---
    result = await middleware(fake_handler, fake_message, data)

    # --- 3️⃣ Проверки ---
    fake_handler.assert_awaited_once_with(fake_message, data)
    assert result == "OK"

    # Проверяем, что bind вызывался с пользователем
    fake_logger.bind.assert_called_with(user=fake_message.from_user.username)
    event_type = type(fake_message).__name__
    logged_msgs = [call.args[0] for call in fake_logger.debug.call_args_list]

    # Проверки формата логов
    assert any(
        f"START {event_type}" in msg for msg in logged_msgs
    ), f"Не найден START лог. Логи: {logged_msgs}"

    assert any(
        f"END {event_type}" in msg for msg in logged_msgs
    ), f"Не найден END лог. Логи: {logged_msgs}"
