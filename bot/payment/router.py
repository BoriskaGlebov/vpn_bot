"""FastAPI-роутер webhook-эндпоинта платёжного провайдера Platega.

В отличие от остальных `*Router` в bot/ (aiogram `Router`, обрабатывающие
апдейты Telegram через `dp.include_router(...)`), этот роутер принимает HTTP-
запросы напрямую от платёжного шлюза, а не от Telegram — поэтому оформлен как
обычный FastAPI `APIRouter` уровня bot-сервиса, по тому же стандарту, что и
роутеры в `api/` (модульный `router`, все зависимости — через `Depends`,
см. `bot/payment/dependencies.py`), и подключается через `app.include_router(router)`
в `bot/main.py`, а не строится фабрикой с замыканием на singleton-объекты.
"""

from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Depends, Request, Response
from loguru._logger import Logger

from bot.app_error.api_error import APIClientConflictError
from bot.payment.dependencies import (
    get_bot_instance,
    get_logger,
    get_payment_service,
    get_payment_webhook_service,
    get_subscription_messages,
)
from bot.payment.dto import PaymentStatus, PaymentWebhookDTO
from bot.payment.services import PaymentService, PaymentWebhookService
from bot.utils.start_stop_bot import send_to_admins

router = APIRouter(prefix="/platega", tags=["webhook"])

PAYMENT_SOURCE_LABELS = {
    "MANUAL": "вручную администратором",
    "GATEWAY": "автоматически платёжным шлюзом",
}


async def _notify_transaction_conflict(
    exc: APIClientConflictError,
    event: PaymentWebhookDTO,
    bot: Bot,
    logger: Logger,
    m_subscription: Any,
) -> None:
    """Разбирает 409-конфликт между вебхуком и текущим статусом транзакции.

    api/ отвечает 409 (`PaymentAlreadyProcessedError`), если транзакция уже
    не в PENDING — то есть кто-то (вебхук раньше, бот, администратор)
    успел изменить её статус первым. Здесь эта гонка классифицируется на
    4 варианта: что говорит текущий вебхук (`webhook_confirms_payment`) и
    в каком статусе транзакция оказалась на самом деле (`transaction_is_paid`).
    Администраторам уходит алерт всегда, кроме мгновенной повторной доставки
    одного и того же PAID-вебхука — иначе ретраи Platega (до 3 раз подряд,
    если не дождалась 200 вовремя) спамили бы одним и тем же сообщением.

    Args:
        exc: Конфликт, полученный от api/ при обработке события.
        event: Событие вебхука, на котором произошёл конфликт.
        bot: Экземпляр бота для отправки алертов администраторам.
        logger: Логгер.
        m_subscription: Секция сообщений `messages.modes.subscription`.

    """
    transaction_id = exc.error.details.get("transaction_id")
    transaction_status = exc.error.details.get("status")
    transaction_source = exc.error.details.get("source")
    source_label = (
        PAYMENT_SOURCE_LABELS.get(transaction_source, transaction_source)
        if transaction_source
        else "неизвестным способом"
    )

    webhook_confirms_payment = event.status == PaymentStatus.PAID
    transaction_is_paid = transaction_status == "PAID"

    if webhook_confirms_payment and transaction_is_paid:
        logger.info(
            "Повторная доставка вебхука уже подтверждённого платежа: "
            "gateway_payment_id={} transaction_id={}",
            event.provider_payment_id,
            transaction_id,
        )
        return

    if webhook_confirms_payment and not transaction_is_paid:
        logger.warning(
            "Webhook подтвердил оплату уже отменённой транзакции: "
            "gateway_payment_id={} transaction_id={} status={}",
            event.provider_payment_id,
            transaction_id,
            transaction_status,
        )
        await send_to_admins(
            bot=bot,
            message_text=m_subscription.gateway_alert.status_conflict.format(
                transaction_id=transaction_id,
                status=transaction_status,
            ),
        )
        return

    if not webhook_confirms_payment and transaction_is_paid:
        logger.warning(
            "Webhook-отмена для транзакции, уже подтверждённой как "
            "оплаченная: gateway_payment_id={} transaction_id={} source={}",
            event.provider_payment_id,
            transaction_id,
            transaction_source,
        )
        await send_to_admins(
            bot=bot,
            message_text=m_subscription.gateway_alert.cancel_after_paid.format(
                transaction_id=transaction_id,
                source=source_label,
            ),
        )
        return

    logger.info(
        "Повторная webhook-отмена для уже отменённой транзакции: "
        "gateway_payment_id={} transaction_id={}",
        event.provider_payment_id,
        transaction_id,
    )
    await send_to_admins(
        bot=bot,
        message_text=m_subscription.gateway_alert.cancel_already_canceled.format(
            transaction_id=transaction_id,
        ),
    )


@router.post("/payment-webhook")
async def payment_webhook(
    request: Request,
    payment_service: PaymentService = Depends(get_payment_service),
    payment_webhook_service: PaymentWebhookService = Depends(
        get_payment_webhook_service
    ),
    bot: Bot = Depends(get_bot_instance),
    logger: Logger = Depends(get_logger),
    m_subscription: Any = Depends(get_subscription_messages),
) -> Response:
    """Принимает вебхук платёжного провайдера Platega и передаёт его на обработку.

    Args:
        request: Входящий HTTP-запрос с телом вебхука.
        payment_service: Сервис платежей (провайдер + подтверждение подлинности).
        payment_webhook_service: Сервис обработки событий вебхука.
        bot: Экземпляр бота (для отправки алертов администраторам).
        logger: Логгер.
        m_subscription: Секция сообщений `messages.modes.subscription`
            (тексты алертов администраторам).

    Returns
        Response: 200 при успешной обработке, включая конфликтные и
        идемпотентные случаи (см. `_notify_transaction_conflict`); 403,
        если подлинность вебхука не подтверждена; 400, если тело вебхука
        не удалось разобрать; 500 при неожиданной ошибке обработки
        (провайдер повторит доставку).

    """
    body: bytes = await request.body()
    if not body:
        logger.debug("Webhook-запрос с пустым телом")
        return Response(
            content="ok",
            media_type="text/plain",
            status_code=200,
        )

    provider = payment_service.provider
    if not await provider.verify_webhook(headers=request.headers, body=body):
        logger.warning("Webhook платёжного провайдера не прошёл проверку подлинности")
        return Response(status_code=403)

    try:
        event = await provider.parse_webhook(body)
    except Exception:
        logger.exception("Не удалось разобрать webhook платёжного провайдера")
        return Response(status_code=400)

    logger.info(
        "Получен webhook платёжного провайдера: gateway_payment_id={} status={}",
        event.provider_payment_id,
        event.status,
    )

    try:
        await payment_webhook_service.handle_event(event)
    except APIClientConflictError as exc:
        await _notify_transaction_conflict(exc, event, bot, logger, m_subscription)
        return Response(status_code=200)
    except Exception:
        logger.exception(
            "Ошибка обработки webhook платёжного провайдера: gateway_payment_id={}",
            event.provider_payment_id,
        )
        await send_to_admins(
            bot=bot,
            message_text=m_subscription.gateway_alert.processing_error.format(
                gateway_payment_id=event.provider_payment_id
            ),
        )
        return Response(status_code=500)

    return Response(status_code=200)
