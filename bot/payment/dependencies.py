from typing import Any

from aiogram import Bot
from fastapi import Depends, Request
from loguru._logger import Logger

from bot.core.config import bot, logger, settings_bot
from bot.core.container import Container
from bot.payment.services import PaymentService, PaymentWebhookService


def get_bot_instance() -> Bot:
    """Возвращает singleton-экземпляр aiogram `Bot`.

    Returns
        Bot: Экземпляр бота (используется для отправки алертов администраторам).

    """
    return bot


def get_logger() -> Logger:
    """Возвращает общий логгер приложения.

    Returns
        Logger: Экземпляр логгера loguru.

    """
    return logger  # type: ignore[return-value]


def get_subscription_messages() -> Any:
    """Возвращает секцию сообщений `messages.modes.subscription`.

    Используется для текстов алертов администраторам
    (`m_subscription.gateway_alert.*`).

    Returns
        Any: Секция конфигурации сообщений подписки.

    """
    return settings_bot.messages.modes.subscription


def get_container(request: Request) -> Container:
    """Возвращает DI-контейнер приложения.

    Контейнер создаётся один раз при старте приложения (`bot/main.py`) и
    кладётся в `app.state.container` — это единственный способ добраться до
    него из FastAPI-зависимостей без циклического импорта `bot.main`
    (именно там контейнер создаётся).

    Args:
        request: Текущий HTTP-запрос.

    Returns
        Container: DI-контейнер приложения.

    """
    return request.app.state.container  # type: ignore[no-any-return]


def get_payment_service(
    container: Container = Depends(get_container),
) -> PaymentService:
    """Возвращает сервис платежей из контейнера приложения.

    Args:
        container: DI-контейнер приложения.

    Returns
        PaymentService: Сервис платежей (провайдер + подтверждение подлинности).

    """
    return container.payment_service


def get_payment_webhook_service(
    container: Container = Depends(get_container),
) -> PaymentWebhookService:
    """Возвращает сервис обработки вебхуков платежей из контейнера приложения.

    Args:
        container: DI-контейнер приложения.

    Returns
        PaymentWebhookService: Сервис обработки событий вебхука.

    """
    return container.payment_webhook_service
