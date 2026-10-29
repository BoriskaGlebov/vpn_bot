import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from aiogram.types import Update
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from bot.admin.router import AdminRouter
from bot.app_error.base_error import AppError
from bot.core.config import bot, dp, logger, settings_bot
from bot.core.container import Container
from bot.core.exceptions.handlers import (
    app_error_handler,
    http_exception_handler,
    request_validation_handler,
    unhandled_exception_handler,
)
from bot.core.schemas import SHealthResponse
from bot.help.router import HelpRouter
from bot.internal.router import router as internal_router
from bot.middleware.exception_middleware import ErrorHandlerMiddleware
from bot.middleware.user_action_middleware import UserActionLoggingMiddleware
from bot.middleware.user_context import UserContextMiddleware
from bot.news.router import NewsRouter
from bot.payment.router import router as payment_router
from bot.referrals.router import ReferralRouter
from bot.scheduler.utils.scheduler_cron import scheduled_check, scheduler
from bot.subscription.router import SubscriptionRouter
from bot.users.router import UserRouter
from bot.utils.start_stop_bot import start_bot, stop_bot
from bot.vpn.router import VPNRouter

tags_metadata: list[dict[str, Any]] = [
    {
        "name": "webhook",
        "description": "Получение обновлений телеграмм.",
    },
    {
        "name": "internal",
        "description": "Внутренний канал api → bot (авторизация X-API-Key).",
    },
]

container = Container(bot=bot)


def _log_resume_broadcast_result(task: asyncio.Task[None]) -> None:
    """Логирует исключение из фоновой задачи возобновления рассылки.

    Без этого колбэка падение `resume_pending_broadcast` в фоне было бы не видно
    нигде — задача ни с чем не связана и её результат никто не ждёт.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("Возобновление рассылки упало в фоне: {}", exc)


@asynccontextmanager
@logger.catch  # type: ignore[misc]
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Менеджер жизненного цикла для FastAPI-приложения.

    Эта функция управляет настройкой и завершением работы бота, включая регистрацию роутеров,
    запуск бота, настройку вебхука и очистку при завершении работы бота.
    """
    logger.info("Запуск настройки бота...")
    await container.init()
    dp.message.middleware(ErrorHandlerMiddleware(logger=logger, bot=bot))  # type: ignore[arg-type]
    dp.callback_query.middleware(ErrorHandlerMiddleware(logger=logger, bot=bot))  # type: ignore[arg-type]
    # log_data управляется отдельным флагом, а не debug_fast_api:
    # debug_fast_api — это отладка FastAPI, а log_data пишет в лог полный
    # repr Telegram-события, то есть текст переписки пользователя.
    log_data = settings_bot.core.log_user_events_data
    log_time = settings_bot.core.debug_fast_api
    dp.message.middleware(
        UserActionLoggingMiddleware(log_data=log_data, log_time=log_time, logger=logger)  # type: ignore[arg-type]
    )
    dp.callback_query.middleware(
        UserActionLoggingMiddleware(log_data=log_data, log_time=log_time, logger=logger)  # type: ignore[arg-type]
    )
    dp.update.middleware(UserContextMiddleware())

    user_router = UserRouter(
        bot=bot,
        logger=logger,  # type: ignore[arg-type]
        redis_manager=container.redis_manager,
        user_service=container.user_service,
        referral_service=container.referral_service,
        admin_service=container.admin_service,
    )

    help_router = HelpRouter(bot=bot, logger=logger, redis=container.redis_manager)  # type: ignore[arg-type]

    admin_router = AdminRouter(
        bot=bot,
        logger=logger,  # type: ignore[arg-type]
        admin_service=container.admin_service,
    )
    subscription_router = SubscriptionRouter(
        bot=bot,
        logger=logger,  # type: ignore[arg-type]
        subscription_service=container.subscription_service,
        referral_service=container.referral_service,
        redis_service=container.redis_admin_mess_storage,
        vpn_service=container.vpn_service,
        payment_mess_storage=container.redis_payment_mess_storage,
    )
    vpn_router = VPNRouter(
        bot=bot,
        logger=logger,  # type: ignore[arg-type]
        vpn_service=container.vpn_service,
        redis=container.redis_manager,
        subscription_service=container.subscription_service,
        user_adapter=container.user_adapter,
    )
    referral_router = ReferralRouter(bot=bot, logger=logger)  # type: ignore[arg-type]
    news_router = NewsRouter(
        bot=bot,
        logger=logger,  # type: ignore[arg-type]
        news_service=container.news_service,
        broadcast_storage=container.redis_news_broadcast_storage,
    )

    dp.include_router(user_router.router)
    dp.include_router(help_router.router)
    dp.include_router(admin_router.router)
    dp.include_router(subscription_router.router)
    dp.include_router(vpn_router.router)
    dp.include_router(referral_router.router)
    dp.include_router(news_router.router)

    # Возобновляем рассылку, прерванную прошлым падением/деплоем, не
    # дожидаясь старта polling/webhook — фоновой задачей, чтобы не блокировать
    # запуск остальной части приложения. Ссылка на задачу сохраняется, иначе
    # event loop держит её только через слабую ссылку и может собрать сборщиком
    # мусора до завершения; колбэк логирует необработанное исключение,
    # которое иначе никуда не всплывёт.
    resume_broadcast_task = asyncio.create_task(news_router.resume_pending_broadcast())
    resume_broadcast_task.add_done_callback(_log_resume_broadcast_result)
    resume_admin_broadcast_task = asyncio.create_task(
        container.admin_broadcast_service.resume_pending_broadcast()
    )
    resume_admin_broadcast_task.add_done_callback(_log_resume_broadcast_result)

    await start_bot(bot=bot)

    scheduler_settings = settings_bot.scheduler
    if scheduler_settings.interval_seconds is not None:
        # Задаётся через app_config.develop.toml / app_config.local.toml —
        # используется для отладки, в проде interval_seconds не задан.
        trigger: IntervalTrigger | CronTrigger = IntervalTrigger(
            seconds=scheduler_settings.interval_seconds
        )
        schedule_description = f"каждые {scheduler_settings.interval_seconds} сек."
    else:
        trigger = CronTrigger(
            hour=scheduler_settings.cron_hour, minute=scheduler_settings.cron_minute
        )
        schedule_description = (
            f"каждый день в {scheduler_settings.cron_hour:02d}:"
            f"{scheduler_settings.cron_minute:02d}"
        )

    scheduler.add_job(
        scheduled_check,
        trigger=trigger,
        kwargs={"service": container.scheduler_bot_service},
        id="scheduled_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("🕒 Планировщик запущен — проверка {}", schedule_description)
    if settings_bot.bot.use_polling:
        await bot.delete_webhook(drop_pending_updates=True)

        logger.warning("Используется поллинг вместо вебхуков!")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    else:
        webhook_url: str = str(settings_bot.bot.webhook_url)
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        logger.info(f"Вебхук установлен на {webhook_url}")

    yield

    logger.info("Завершение работы бота...")
    if not resume_broadcast_task.done():
        resume_broadcast_task.cancel()
    if not resume_admin_broadcast_task.done():
        resume_admin_broadcast_task.cancel()
    try:
        await bot.delete_webhook()
        logger.info("Вебхук удалён")
    except Exception as e:
        logger.exception(f"Ошибка при удалении вебхука: {e}")
    try:
        await stop_bot(bot=bot)
        logger.info("Бот остановлен")
    except Exception as e:
        logger.exception(f"Ошибка при остановке бота: {e}")
    try:
        await container.shutdown()
        logger.info("Отключение от Redis и API")
    except Exception as e:
        logger.exception(f"Ошибка при отключении от Redis: {e}")
    try:
        scheduler.shutdown(wait=False)
    except Exception as e:
        logger.exception(f"Ошибка при отключении Scheduler: {e}")


app: FastAPI = FastAPI(
    debug=settings_bot.core.debug_fast_api,
    title="VPN Boriska Bot",
    root_path="/bot",
    summary="Бот, который раздает конфигурационные файлы для Amnezia VPN",
    description="""
---
# VPN Boriska Bot
___
Этот бот предназначен для управления доступом к VPN-сервису.
Он позволяет пользователям получать новые конфигурации, напоминать старые и оплачивать доступ.

## Основные функции:
- Выдача новых VPN-конфигураций пользователям
- Напоминание о действующих/старых конфигурациях
- Управление оплатой доступа к VPN
- Администрирование через Telegram
    """,
    openapi_tags=tags_metadata,
    contact={
        "name": "Boriska Glebov",
        "url": "http://localhost:8000/bot/docs",
        "email": "BorisTheBlade.glebov@yandex.ru",
    },
    lifespan=lifespan,
)

# Контейнер кладётся в app.state, чтобы FastAPI-зависимости payment-роутера
# (bot/payment/dependencies.py) могли получить его через Request без
# циклического импорта bot.main (см. get_container).
app.state.container = container

app.include_router(payment_router)
app.include_router(internal_router)

app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.post(
    "/webhook",
    tags=[
        "webhook",
    ],
)
async def webhook(request: Request) -> Response:
    """Обработчик входящих webhook-обновлений Telegram.

    Эндпоинт принимает POST-запросы от Telegram, валидирует полученные
    обновления и передаёт их в диспетчер aiogram.

    Пустое тело запроса считается штатным и подтверждается HTTP 200 без
    дальнейшей обработки. Если тело непустое, но не проходит валидацию как
    Telegram Update (ValidationError/ValueError), обработчик возвращает
    HTTP 500 — Telegram в этом случае повторит доставку обновления.

    Args:
        request: Входящий запрос FastAPI с payload обновления Telegram.

    Returns
        Ответ FastAPI со статусом HTTP 200 в штатном случае или HTTP 500,
        если payload не прошёл валидацию.

    """
    body: bytes = await request.body()
    if not body:
        logger.debug("Webhook-запрос с пустым телом")
        return Response(
            content="ok",
            media_type="text/plain",
            status_code=200,
        )

    try:
        update: Update = Update.model_validate_json(
            body,
            context={"bot": bot},
        )
    except (ValidationError, ValueError):
        logger.exception("Некорректный payload webhook от Telegram")
        return Response(status_code=500)

    await dp.feed_update(bot, update)

    logger.debug("Webhook-обновление успешно обработано")
    return Response(status_code=200)


@app.get(
    "/health",
    response_model=SHealthResponse,
    tags=[
        "webhook",
    ],
    summary="Проверка здоровья сервиса",
)
async def health() -> JSONResponse:
    """Проверка здоровья приложения.

    Эндпоинт для проверки работоспособности FastAPI-приложения.

    Возвращает текущий статус сервиса, чтобы использовать
    для мониторинга и Docker HEALTHCHECK.

    Returns
        JSON с полями:
        - status: "ok" если сервис работает
        - message: описание статуса

    """
    return JSONResponse(
        status_code=200,
        content={"status": "ok", "message": "FastAPI service is running"},
    )


if __name__ == "__main__":
    uvicorn.run(
        app="bot.main:app",
        host="0.0.0.0",
        port=8088,
        reload=settings_bot.core.reload_fast_api,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
