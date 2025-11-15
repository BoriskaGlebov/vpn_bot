from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from aiogram.types import Update
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Request

from bot.admin.router import AdminRouter
from bot.admin.services import AdminService
from bot.config import bot, dp, logger, settings_bot
from bot.help.router import HelpRouter
from bot.middleware.exception_middleware import ErrorHandlerMiddleware
from bot.middleware.user_action_middleware import UserActionLoggingMiddleware
from bot.redis_manager import redis_manager
from bot.subscription.router import SubscriptionRouter
from bot.subscription.services import SubscriptionService
from bot.subscription.utils.scheduler_cron import scheduled_check, scheduler
from bot.users.router import UserRouter
from bot.users.services import UserService
from bot.utils.init_default_roles import init_default_roles
from bot.utils.start_stop_bot import start_bot, stop_bot
from bot.vpn.router import VPNRouter
from bot.vpn.services import VPNService

#
# API теги и их описание
tags_metadata: list[dict[str, Any]] = [
    {
        "name": "webhook",
        "description": "Получение обновлений телеграмм",
    },
]


@asynccontextmanager
@logger.catch  # type: ignore[misc]
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Менеджер жизненного цикла для FastAPI-приложения.

    Эта функция управляет настройкой и завершением работы бота, включая регистрацию роутеров,
    запуск бота, настройку вебхука и очистку при завершении работы.
    """
    logger.info("Запуск настройки бота...")
    await redis_manager.connect()
    dp.message.middleware(ErrorHandlerMiddleware(logger=logger, bot=bot))
    dp.callback_query.middleware(ErrorHandlerMiddleware(logger=logger, bot=bot))
    dp.message.middleware(
        UserActionLoggingMiddleware(log_data=True, log_time=True, logger=logger)
    )
    dp.callback_query.middleware(
        UserActionLoggingMiddleware(log_data=True, log_time=True, logger=logger)
    )

    user_service = UserService(redis=redis_manager)
    user_router = UserRouter(
        bot=bot, logger=logger, redis_manager=redis_manager, user_service=user_service
    )

    help_router = HelpRouter(bot=bot, logger=logger)

    admin_service = AdminService()
    admin_router = AdminRouter(bot=bot, logger=logger, admin_service=admin_service)

    subscription_service = SubscriptionService(bot=bot, logger=logger)
    subscription_router = SubscriptionRouter(
        bot=bot, logger=logger, subscription_service=subscription_service
    )
    vpn_service = VPNService()
    vpn_router = VPNRouter(bot=bot, logger=logger, vpn_service=vpn_service)

    dp.include_router(user_router.router)
    dp.include_router(help_router.router)
    dp.include_router(admin_router.router)
    dp.include_router(subscription_router.router)
    dp.include_router(vpn_router.router)

    await init_default_roles()  # type: ignore
    await start_bot(bot=bot)
    scheduler.add_job(
        scheduled_check,
        trigger=IntervalTrigger(minutes=1),
        kwargs={"logger": logger},
    )
    scheduler.start()
    logger.info("🕒 Планировщик запущен — проверка каждые 1 минуту")
    if settings_bot.USE_POLLING:
        await bot.delete_webhook(drop_pending_updates=True)

        logger.warning("Используется поллинг вместо вебхуков!")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    else:
        webhook_url: str = str(settings_bot.WEBHOOK_URL)
        await bot.set_webhook(
            url=webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True,
        )
        logger.info(f"Вебхук установлен на {webhook_url}")

    yield

    logger.info("Завершение работы бота...")
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
        await redis_manager.disconnect()
    except Exception as e:
        logger.exception(f"Ошибка при отключении от Redis: {e}")
    try:
        scheduler.shutdown(wait=False)
    except Exception as e:
        logger.exception(f"Ошибка при отключении Scheduler: {e}")


# Метаданные для OpenAPI
app: FastAPI = FastAPI(
    debug=settings_bot.DEBUG_FAST_API,
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

API предоставляет доступ к функционалу бота и позволяет автоматизировать
взаимодействие с VPN-сервисом.
    """,
    openapi_tags=tags_metadata,
    contact={
        "name": "Boriska Glebov",
        "url": "http://localhost:8000/bot/docs",
        "email": "BorisTheBlade.glebov@yandex.ru",
    },
    lifespan=lifespan,
)


@app.post("/webhook")  # type: ignore[misc]
@logger.catch  # type: ignore[misc]
async def webhook(request: Request) -> None:
    """Обработчик вебхуков от Telegram.

    Получает обновления от Telegram,
    валидирует их и передает в диспетчер Aiogram.


    Args:
        request: Запрос FastAPI с JSON-данными от Telegram

    Returns: None

    """
    logger.debug("Получен запрос вебхука")
    update: Update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    logger.debug("Обновление обработано")


if __name__ == "__main__":
    """
    Точка входа для запуска FastAPI-приложения.

    Запускает сервер Uvicorn с приложением FastAPI.
    """
    uvicorn.run(
        app="bot.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings_bot.RELOAD_FAST_API,
    )
