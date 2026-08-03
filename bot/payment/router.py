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
from bot.payment.dto import PaymentStatus
from bot.payment.services import PaymentService, PaymentWebhookService
from bot.utils.start_stop_bot import send_to_admins

router = APIRouter(prefix="/platega", tags=["webhook"])


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
        Response: 200 при успешной обработке, включая идемпотентные
        случаи — повторную доставку уже обработанного платежа, а также
        вебхук-отмену (например, автоотмену Platega платёжной сессии
        после ~30 минут бездействия) для транзакции, которая уже в
        финальном статусе (отменена другим путём или уже оплачена
        переводом) — отменять в таком случае нечего, это не ошибка; 403,
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
        # api/ отвечает 409, если транзакция уже не в PENDING (см.
        # `PaymentService._ensure_pending` на api-стороне) — это касается
        # и подтверждения, и отмены: конфликт возникает при любой попытке
        # повторно изменить статус уже финализированной транзакции.
        conflict_status = exc.error.details.get("status")

        if event.status != PaymentStatus.PAID:
            # Сам вебхук — отмена/чарджбэк, а не подтверждение оплаты.
            # Platega, например, сама отменяет платёжную сессию после
            # ~30 минут бездействия пользователя — к этому моменту
            # транзакция уже могла быть отменена другим путём (повторная
            # доставка того же вебхука) или уже оплачена переводом и
            # подтверждена администратором. В обоих случаях отменять
            # нечего и денег никто не теряет — штатная идемпотентная
            # ситуация, не повод для алерта администраторам.
            logger.info(
                "Webhook-отмена для транзакции с уже финальным статусом: "
                "gateway_payment_id={} current_status={}",
                event.provider_payment_id,
                conflict_status,
            )
            return Response(status_code=200)

        if conflict_status == "PAID":
            # Harmless: повторная доставка уже обработанного платежа
            # (Platega повторяет вебхук до 3 раз, если не получила 200
            # вовремя) — идемпотентно подтверждаем получение.
            logger.info(
                "Webhook платёжного провайдера уже был обработан ранее: "
                "gateway_payment_id={}",
                event.provider_payment_id,
            )
        else:
            # Вебхук пытается подтвердить оплату транзакции, которая уже
            # отменена/провалена — гонка между действием бота/пользователя
            # и вебхуком. Деньги могли поступить, а услуга не
            # предоставлена — нужна ручная проверка администратором
            # (см. PaymentService.confirm_transaction).
            logger.warning(
                "Webhook подтвердил оплату уже отменённой транзакции: "
                "gateway_payment_id={} status={}",
                event.provider_payment_id,
                conflict_status,
            )
            await send_to_admins(
                bot=bot,
                message_text=m_subscription.gateway_alert.status_conflict.format(
                    transaction_id=exc.error.details.get("transaction_id"),
                    status=conflict_status,
                ),
            )
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
