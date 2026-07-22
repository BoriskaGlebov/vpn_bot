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
    APIError,
)
from api.app_error.base_error import (
    AppError,
)
from api.core.config import settings_api
from api.core.database import engine
from api.core.exceptions.handlers.business import app_error_handler
from api.core.exceptions.handlers.http import (
    api_error_handler,
    database_exception_handler,
    request_validation_handler,
    unhandled_exception_handler,
)
from api.core.schemas import SHealthResponse
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.exceptions_middleware import ExceptionLoggingMiddleware
from api.middleware.logg_router_middleware import RequestLoggingMiddleware
from api.middleware.logger_context import LogContextMiddleware
from api.middleware.session_middleware import DBSessionMiddleware
from api.news.router import router as news_router
from api.payment.admin import PaymentTransactionAdmin
from api.payment.router import router as payment_router
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
        "description": "Общий тег для всех эндпоинтов, используемых Telegram-ботом",
    },
    {
        "name": "USERS",
        "description": "Управление пользователями: регистрация, получение информации, обновление профиля",
    },
    {
        "name": "ADMIN",
        "description": "Административные функции: управление пользователями, ролями, аналитика доходов",
    },
    {
        "name": "SUBSCRIPTION",
        "description": "Управление подписками: создание, продление, получение информации о тарифах",
    },
    {
        "name": "VPN",
        "description": "Управление VPN-конфигурациями: создание, удаление, получение конфигов пользователей",
    },
    {
        "name": "REFERRALS",
        "description": "Реферальная система: получение реферальных ссылок, статистики, начисление бонусов",
    },
    {
        "name": "PAYMENT",
        "description": "Платежная система: создание платежей, подтверждение транзакций, история платежей",
    },
    {
        "name": "NEWS",
        "description": "Управление новостями и уведомлениями для пользователей",
    },
    {
        "name": "SCHEDULER",
        "description": "Планировщик задач: управление отложенными операциями и периодическими задачами",
    },
    {
        "name": "system",
        "description": "Служебные методы: health-check, мониторинг состояния сервиса",
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
    debug=settings_api.core.debug_fast_api,
    title="VPN Boriska API",
    version="1.0.0",
    root_path="/api",
    summary="API для управления VPN-сервисом с интеграцией Telegram-бота",
    description="""
## 📡 VPN Boriska API

Сервис предоставляет HTTP API для управления VPN-подписками через Telegram-бота.

### Основные модули:

#### 👥 Пользователи (`/users`)
- Регистрация и аутентификация пользователей
- Управление профилями
- Получение информации о пользователе

#### 🔐 Администрирование (`/admin`)
- Управление пользователями и ролями
- Продление подписок
- Аналитика доходов
- Доступ только для администраторов

#### 📅 Подписки (`/subscriptions`)
- Создание и продление подписок
- Получение информации о тарифах
- Управление пробными периодами
- История подписок пользователя

#### 🌐 VPN (`/vpn`)
- Создание VPN-конфигураций
- Удаление конфигов
- Получение списка активных конфигов
- Управление лимитами устройств

#### 🎁 Реферальная система (`/referrals`)
- Генерация реферальных ссылок
- Отслеживание рефералов
- Начисление бонусов
- Статистика по рефералам

#### 💳 Платежи (`/payment`)
- Создание платежных транзакций
- Подтверждение оплаты
- История платежей
- Интеграция с платежными системами

#### 📰 Новости (`/news`)
- Публикация новостей и уведомлений
- Рассылка сообщений пользователям

#### ⏰ Планировщик (`/scheduler`)
- Управление отложенными задачами
- Периодические операции
- Автоматизация процессов

#### ⚙️ Системные эндпоинты
- `/health` — проверка состояния сервиса
- Мониторинг и диагностика

---

### 🔒 Безопасность

Большинство эндпоинтов требуют аутентификации через Telegram.
Административные функции доступны только пользователям с ролью `admin` или `founder`.

### 📊 Формат ответов

Все ошибки возвращаются в унифицированном формате:
```json
{
  "error": {
    "code": "error_code",
    "message": "Описание ошибки",
    "details": {}
  }
}
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
app.include_router(payment_router)


app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

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
admin.add_view(PaymentTransactionAdmin)


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
        reload=settings_api.core.reload_fast_api,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )

# TODO проблема перезапуска бота он не может корректно стартовать изза того что в контейнер ключи от  ssh агента не получает
# TODO подтверждение при оплате надо доавить когда делает админ а когнда нет
# TODO отдельного пользвателя на Xray
# TODO пользователь без подписки не может получить бесплатнывй прокси? пока не работает надо удалить?
# TODO Почему то founder получает цену не как founder а как standard
# При переходе между оплатными  стадиями у премиумов проблемы с ценами
# Нало этот проработать плюс цвета founder в админке поменяй
