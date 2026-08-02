from typing import Any

from aiogram import Bot
from fastapi import APIRouter, Request, Response
from loguru._logger import Logger

from bot.app_error.api_error import APIClientConflictError
from bot.payment.services import PaymentService, PaymentWebhookService
from bot.utils.start_stop_bot import send_to_admins


def build_payment_router(
    bot: Bot,
    logger: Logger,
    payment_service: PaymentService,
    payment_webhook_service: PaymentWebhookService,
    m_subscription: Any,
) -> APIRouter:
    """Собирает FastAPI-роутер с webhook-эндпоинтом платёжного провайдера.

    В отличие от остальных `*Router` в bot/ (aiogram `Router`, обрабатывающие
    апдейты Telegram), это FastAPI `APIRouter` уровня bot-сервиса — сам
    эндпоинт принимает HTTP-запросы напрямую от платёжного шлюза, а не от
    Telegram. Поэтому роутер — фабричная функция, а не подкласс `BaseRouter`
    (который заточен под регистрацию aiogram-хендлеров).

    Args:
        bot: Экземпляр бота (для отправки алертов администраторам).
        logger: Логгер.
        payment_service: Сервис платежей (провайдер + подтверждение подлинности).
        payment_webhook_service: Сервис обработки событий вебхука.
        m_subscription: Секция сообщений `messages.modes.subscription`
            (тексты алертов администраторам).

    Returns
        APIRouter: Роутер с зарегистрированным `POST /payment-webhook`.

    """
    router = APIRouter(tags=["webhook"])

    @router.post("/payment-webhook")
    async def payment_webhook(request: Request) -> Response:
        """Принимает вебхук платёжного провайдера и передаёт его на обработку.

        Args:
            request (Request): Входящий HTTP-запрос с телом вебхука.

        Returns
            Response: 200 при успешной обработке (в том числе повторной
            доставке уже обработанного платежа); 403, если подлинность
            вебхука не подтверждена; 400, если тело вебхука не удалось
            разобрать; 500 при неожиданной ошибке обработки (провайдер
            повторит доставку).

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
            logger.warning(
                "Webhook платёжного провайдера не прошёл проверку подлинности"
            )
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
            # api/ отвечает 409 в двух разных по серьёзности случаях, отличить
            # можно по статусу транзакции в details (см. PaymentAlreadyProcessedError).
            conflict_status = exc.error.details.get("status")
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
                # Транзакцию отменили раньше, чем пришло подтверждение оплаты —
                # гонка между действием бота/пользователя и вебхуком. Деньги
                # могли поступить, а услуга не предоставлена — нужна ручная
                # проверка администратором (см. PaymentService.confirm_transaction).
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

    return router
