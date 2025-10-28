from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from aiogram.types import Update
from fastapi import FastAPI, Request

from bot.admin.router import AdminRouter

# from bot.admin.router import admin_router
from bot.config import bot, dp, logger, settings_bot
from bot.help.router import HelpRouter
from bot.middleware.exception_middleware import ErrorHandlerMiddleware
from bot.middleware.user_action_middleware import UserActionLoggingMiddleware
from bot.redis_manager import redis_manager

# from bot.subscription.router import subscription_router
from bot.users.router import UserRouter
from bot.utils.init_default_roles import init_default_roles
from bot.utils.start_stop_bot import start_bot, stop_bot

# from bot.vpn.router import vpn_router
# from bot.vpn.router import VPNRouter

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
    dp.message.middleware(ErrorHandlerMiddleware())
    dp.message.middleware(UserActionLoggingMiddleware(log_data=True, log_time=True))
    dp.callback_query.middleware(
        UserActionLoggingMiddleware(log_data=True, log_time=True)
    )
    dp.callback_query.middleware(ErrorHandlerMiddleware())
    user_router = UserRouter(bot=bot, logger=logger, redis_manager=redis_manager)
    help_router = HelpRouter(bot=bot, logger=logger)
    admin_router = AdminRouter(bot=bot, logger=logger)
    dp.include_router(user_router.router)
    dp.include_router(help_router.router)
    dp.include_router(admin_router.router)
    # dp.include_router(subscription_router)
    # vpn_router = VPNRouter()
    # dp.include_router(vpn_router.router)
    #
    #

    await init_default_roles()  # type: ignore
    await start_bot()
    if settings_bot.USE_POLING:
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
        await stop_bot()
        logger.info("Бот остановлен")
    except Exception as e:
        logger.exception(f"Ошибка при остановке бота: {e}")
    try:
        await redis_manager.disconnect()
    except Exception as e:
        logger.exception(f"Ошибка при отключении от Redis: {e}")


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
    logger.info("Получен запрос вебхука")
    update: Update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    logger.info("Обновление обработано")


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
