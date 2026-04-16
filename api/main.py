from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from loguru import logger
from sqladmin import Admin
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import JSONResponse
from starlette.templating import Jinja2Templates

from api.admin.router import router as admin_router
from api.app_error.api_error import (
    AdminNotFoundHeaderError,
    MissingTelegramHeaderError,
    UserNotFoundHeaderError,
)
from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    ReferralError,
    SubscriptionNotFoundError,
    TrialAlreadyUsedError,
    UserNotFoundError,
    VPNLimitError,
)
from api.core.config import settings_api
from api.core.database import engine
from api.core.exceptions.handlers.business import (
    active_subscription_exists_handler,
    referral_exception_handler,
    subscription_not_found_handler,
    trial_already_used_handler,
    user_not_found_handler,
    vpn_limit_handler,
)
from api.core.exceptions.handlers.http import (
    database_exception_handler,
    missing_telegram_header_handler,
    request_validation_handler,
    unregistered_user_handler,
    user_not_admin_handler,
)
from api.core.schemas import SHealthResponse
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.exceptions_middleware import ExceptionLoggingMiddleware
from api.middleware.logg_router_middleware import RequestLoggingMiddleware
from api.middleware.logger_context import LogContextMiddleware
from api.middleware.session_middleware import DBSessionMiddleware
from api.news.router import router as news_router
from api.referrals.admin import ReferralAdmin
from api.referrals.router import router as referrals_router
from api.scheduler.router import router as scheduler_router
from api.subscription.admin import SubscriptionAdmin
from api.subscription.router import router as subscription_router
from api.users.admin import RoleAdmin, UserAdmin
from api.users.auth_admin import AdminAuth
from api.users.router import router as user_router
from api.users.utils.init_default_roles import init_default_roles_admins
from api.vpn.admin import VPNConfigAdmin
from api.vpn.router import router as vpn_router

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
    await init_default_roles_admins()  # type: ignore
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
app.include_router(admin_router)
app.include_router(subscription_router)
app.include_router(referrals_router)
app.include_router(vpn_router)
app.include_router(news_router)
app.include_router(scheduler_router)

app.add_exception_handler(UserNotFoundError, user_not_found_handler)
app.add_exception_handler(SubscriptionNotFoundError, subscription_not_found_handler)

app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(
    ActiveSubscriptionExistsError, active_subscription_exists_handler
)
app.add_exception_handler(TrialAlreadyUsedError, trial_already_used_handler)
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(ReferralError, referral_exception_handler)
app.add_exception_handler(VPNLimitError, vpn_limit_handler)
app.add_exception_handler(MissingTelegramHeaderError, missing_telegram_header_handler)
app.add_exception_handler(UserNotFoundHeaderError, unregistered_user_handler)
app.add_exception_handler(AdminNotFoundHeaderError, user_not_admin_handler)

app.add_middleware(LogContextMiddleware)
app.add_middleware(AuthMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(DBSessionMiddleware)

app.add_middleware(ExceptionLoggingMiddleware)


authentication_backend = AdminAuth(
    secret_key=settings_api.session_secret.get_secret_value()
)

templates = Jinja2Templates(directory="api/templates")
admin = Admin(
    app,
    engine,
    title="Админ панель Админа",
    templates_dir="api/templates",
    authentication_backend=authentication_backend,
)
admin.add_view(UserAdmin)
admin.add_view(RoleAdmin)
admin.add_view(SubscriptionAdmin)
admin.add_view(VPNConfigAdmin)
admin.add_view(ReferralAdmin)


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
