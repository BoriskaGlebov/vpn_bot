from contextlib import asynccontextmanager
from typing import Any, Dict, List

import uvicorn
from aiogram.types import Update
from fastapi import FastAPI, Request

from bot.config import bot, dp, logger, settings_bot
from bot.help.router import help_router
from bot.utils.start_stop_bot import start_bot, stop_bot

# API теги и их описание
tags_metadata: List[Dict[str, Any]] = [
    {
        "name": "webhook",
        "description": "Получение обновлений телеграмм",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Менеджер жизненного цикла для FastAPI-приложения.

    Эта функция управляет настройкой и завершением работы бота, включая регистрацию роутеров,
    запуск бота, настройку вебхука и очистку при завершении работы.
    """
    logger.info("Запуск настройки бота...")
    dp.include_router(help_router)
    await start_bot()
    webhook_url: str = settings_bot.get_webhook_url()
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


# static_dir = os.path.abspath(os.path.join(settings.BASE_DIR, "api", "static"))
# app.mount("/static", StaticFiles(directory=static_dir), name="static")
#
# app.include_router(public_offer_router)
# app.include_router(payments_router)


@app.post("/webhook")
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
