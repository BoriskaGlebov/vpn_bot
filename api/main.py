from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from loguru import logger
from starlette.responses import JSONResponse

from api.config import settings_api
from api.users.router import router as user_router
from shared.schemas.health_check import SHealthResponse

# API теги и их описание
tags_metadata: list[dict[str, Any]] = [
    {
        "name": "bot",
        "description": "Методы для взаимодействия с Telegram-ботом (отправка событий, управление состояниями).",
    },
    {
        "name": "llm",
        "description": "Методы для AI-агента (обработка сообщений, генерация ответов, выполнение действий).",
    },
    {
        "name": "system",
        "description": "Служебные методы (health-check, мониторинг).",
    },
]


@asynccontextmanager
@logger.catch  # type: ignore[misc]
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Менеджер жизненного цикла для FastAPI-приложения.

    Эта функция управляет настройкой и завершением работы бота, включая регистрацию роутеров,
    запуск бота, настройку вебхука и очистку при завершении работы бота.
    """
    logger.info("Запуск настройки api сервиса VPN Boriska...")

    yield

    logger.info("Завершение работы api сервиса VPN Boriska...")


# Метаданные для OpenAPI
app: FastAPI = FastAPI(
    debug=settings_api.debug_fast_api,
    title="VPN Boriska API",
    version="1.0.0",
    root_path="/api",
    summary="API для взаимодействия с ботом и AI-агентом",
    description="""
## 📡 Boriska API

Сервис предоставляет HTTP API для взаимодействия между внутренними компонентами системы.

### Основные направления:

### 🤖 Bot API
Методы для интеграции с Telegram-ботом:
- отправка событий
- управление пользователями
- триггер действий

### 🧠 LLM API
Методы для AI-агента:
- обработка пользовательских сообщений
- генерация ответов
- выполнение команд

### ⚙️ System API
Служебные эндпоинты:
- проверка состояния сервиса
- мониторинг

---

Сервис предназначен для использования внутренними компонентами (bot, workers, AI-agent).
    """,
    openapi_tags=tags_metadata,
    contact={
        "name": "Boriska Glebov",
        "url": "https://help-blocks.ru/bot/docs",
        "email": "BorisTheBlade.Glebov@yandex.ru",
    },
    lifespan=lifespan,
)
app.include_router(user_router)


@app.get(
    "/health",
    response_model=SHealthResponse,
    tags=[
        "system",
    ],
    summary="Проверка состояния сервиса",
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
        content={"status": "ok", "message": "API service is running"},
    )


if __name__ == "__main__":
    """
    Точка входа для запуска FastAPI-приложения.

    Запускает сервер Uvicorn с приложением FastAPI.
    """
    uvicorn.run(
        app="api.main:app",
        host="0.0.0.0",
        port=8089,
        reload=settings_api.reload_fast_api,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
