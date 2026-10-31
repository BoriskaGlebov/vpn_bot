from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from loguru import logger
from sqladmin import Admin
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from api.admin.badges import (
    EXPENSE_CATEGORY_BADGE_COLORS,
    EXPENSE_CATEGORY_LABELS,
    PAYMENT_BADGE_COLORS,
    PROMO_DISCOUNT_TYPE_COLORS,
    PROMO_DISCOUNT_TYPE_LABELS,
    ROLE_BADGE_COLORS,
    SUBSCRIPTION_BADGE_COLORS,
    VPN_BACKEND_BADGE_COLORS,
    VPN_BACKEND_LABELS,
    VPN_CONFIG_BADGE_COLORS,
    VPN_CONFIG_STATUS_LABELS,
    VPN_PROTOCOL_LABELS,
)
from api.admin.dashboard import DashboardView
from api.admin.finance_dashboard import FinanceDashboardView
from api.admin.navigation import resolve_back_url
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
    http_exception_handler,
    request_validation_handler,
    unhandled_exception_handler,
)
from api.core.schemas import SHealthResponse
from api.expense.admin import ExpenseAdmin
from api.expense.router import router as expense_router
from api.finance.router import router as finance_router
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.exceptions_middleware import ExceptionLoggingMiddleware
from api.middleware.logg_router_middleware import RequestLoggingMiddleware
from api.middleware.logger_context import LogContextMiddleware
from api.middleware.session_middleware import DBSessionMiddleware
from api.news.router import router as news_router
from api.payment.admin import PaymentTransactionAdmin
from api.payment.router import router as payment_router
from api.promo.admin import PromoCodeAdmin, PromoCodeUsageAdmin
from api.promo.router import router as promo_router
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
        "name": "PROMO",
        "description": "Промокоды на скидку: проверка применимости и расчёт скидки",
    },
    {
        "name": "EXPENSES",
        "description": "Учёт расходов: создание, редактирование, удаление, агрегация по месяцам",
    },
    {
        "name": "FINANCE",
        "description": "Финансовая аналитика: P&L, годовой итог, ARPU, безубыточность, тренд выручки",
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
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Менеджер жизненного цикла для FastAPI-приложения.

    Эта функция управляет настройкой и завершением работы бота, включая регистрацию роутеров,
    запуск бота, настройку вебхука и очистку при завершении работы бота.

    Ошибка инициализации (`init_default_roles_admins`) пробрасывается дальше,
    чтобы приложение не поднялось в нерабочем состоянии — раньше здесь стоял
    `@logger.catch` поверх генератора, который на деле не перехватывал
    исключения после `yield`/до него (он оборачивал только создание объекта
    генератора, не его выполнение) и тем более не останавливал бы старт
    приложения, даже если бы сработал (`reraise=False` по умолчанию).
    """
    logger.info("Запуск настройки api сервиса VPN Boriska...")
    try:
        await init_default_roles_admins()  # type: ignore
    except Exception:
        logger.exception("Не удалось запустить api сервис VPN Boriska")
        raise
    logger.info("Api сервис VPN Boriska успешно запущен")

    yield

    logger.info("Завершение работы api сервиса VPN Boriska...")


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

#### 🏷️ Промокоды (`/promo`)
- Проверка применимости промокода
- Расчёт скидки от базовой суммы

#### 💸 Расходы (`/expenses`)
- Учёт расходов на инфраструктуру (серверы, домены, IP, AI, реклама)
- Фильтрация по категории и ноде
- Агрегация расходов по месяцам за год
- Доступ только для администраторов

#### 📊 Финансовая аналитика (`/finance`)
- P&L по месяцам (выручка, расходы, прибыль, маржа)
- Годовой итог: доход, расход, средний чек, ARPU, конверсия в платящих
- Точка безубыточности: сколько платежей нужно в месяц
- MoM-тренд выручки за последние N месяцев

#### ⚙️ Системные эндпоинты
- `/health` — проверка состояния сервиса
- Мониторинг и диагностика

---

### 🔒 Безопасность

Приватные эндпоинты требуют **два** заголовка одновременно:

- `X-Internal-Secret` — общий секрет между Telegram-ботом и этим API.
  Без него `X-Telegram-Id` не принимается во внимание вообще — так
  закрыт обход авторизации подделкой чужого Telegram ID. Секрет знает
  только сам бот, публично он не раздаётся.
- `X-Telegram-Id` — Telegram ID пользователя, от чьего имени выполняется запрос.

Оба заголовка можно ввести через кнопку **Authorize** в этом Swagger UI
и проверить работу эндпоинтов прямо отсюда.

Административные функции дополнительно требуют роль `admin` или `founder`
у пользователя, определённого по `X-Telegram-Id`.

### 📊 Формат ответов

Любая ошибка API — от бизнес-логики до 404/405 на уровне маршрутизации —
возвращается в одном и том же формате:
```json
{
  "error": {
    "code": "error_code",
    "message": "Описание ошибки",
    "details": {}
  }
}
```

Наиболее частые коды ошибок:

| `code` | HTTP | Когда возникает |
|---|---|---|
| `invalid_internal_secret` | 401 | Заголовок `X-Internal-Secret` отсутствует или неверен |
| `missing_telegram_header` | 403 | Заголовок `X-Telegram-Id` отсутствует |
| `admin_access_denied` | 403 | У пользователя нет роли `admin`/`founder` |
| `user_not_found` | 404 | Пользователь с указанным `X-Telegram-Id` не зарегистрирован |
| `validation_error` | 422 | Некорректное тело запроса / параметры |
| `expense_not_found` | 404 | Запись о расходе с указанным ID не найдена |
| `invalid_node_name` | 422 | Имя ноды не найдено в конфигурации `vpn.nodes` |
| `http_exception` | 404/405/... | Ошибка маршрутизации (несуществующий путь, неверный метод) |
| `database_error` | 500 | Ошибка при обращении к базе данных |
| `internal_error` | 500 | Любая другая непредвиденная ошибка |
    """,
    openapi_tags=tags_metadata,
    contact={
        "name": "Boriska Glebov",
        "url": "https://boris-guard.pro/api/docs",
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
app.include_router(promo_router)
app.include_router(expense_router)
app.include_router(finance_router)


app.add_exception_handler(APIError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
app.add_exception_handler(SQLAlchemyError, database_exception_handler)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Starlette выполняет middleware в порядке, ОБРАТНОМ вызовам add_middleware —
# каждый новый добавляется в начало списка (значит, выполняется раньше).
# Реальный порядок выполнения на входящий запрос (снаружи внутрь):
#   ExceptionLoggingMiddleware -> DBSessionMiddleware -> AuthMiddleware ->
#   LogContextMiddleware -> RequestLoggingMiddleware -> роут.
# Это важно для логов: AuthMiddleware должен успеть отработать раньше
# LogContextMiddleware (тот читает request.state.user, который выставляет
# Auth), а LogContextMiddleware — раньше RequestLoggingMiddleware (иначе его
# логи "Начало/Завершен запрос" всегда пишутся с user=undefined_user).
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(LogContextMiddleware)
app.add_middleware(AuthMiddleware)
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
# SQLAdmin монтирует "/statics" под фиксированный StaticFiles(packages=["sqladmin"])
# (см. sqladmin.application.Admin.__init__) — свою директорию туда не подставить.
# Mount регистрируется на ВНЕШНЕМ app, а не на admin.admin: Starlette кладёт
# в scope только САМЫЙ ПЕРВЫЙ встреченный router (routing.py: `if "router" not
# in scope: scope["router"] = self"), им всегда оказывается router внешнего
# FastAPI-приложения — url_for из шаблонов админки резолвит имена маршрутов
# именно через него, независимо от вложенности Mount'ов.
app.mount(
    "/admin-static",
    StaticFiles(directory="api/static"),
    name="admin_custom_static",
)
admin.templates.env.globals["back_url"] = resolve_back_url
admin.templates.env.globals["role_badge_colors"] = ROLE_BADGE_COLORS
admin.templates.env.globals["subscription_badge_colors"] = SUBSCRIPTION_BADGE_COLORS
admin.templates.env.globals["payment_badge_colors"] = PAYMENT_BADGE_COLORS
admin.templates.env.globals["vpn_config_badge_colors"] = VPN_CONFIG_BADGE_COLORS
admin.templates.env.globals["vpn_config_status_labels"] = VPN_CONFIG_STATUS_LABELS
admin.templates.env.globals["vpn_backend_badge_colors"] = VPN_BACKEND_BADGE_COLORS
admin.templates.env.globals["vpn_backend_labels"] = VPN_BACKEND_LABELS
admin.templates.env.globals["vpn_protocol_labels"] = VPN_PROTOCOL_LABELS
admin.templates.env.globals["promo_discount_type_colors"] = PROMO_DISCOUNT_TYPE_COLORS
admin.templates.env.globals["promo_discount_type_labels"] = PROMO_DISCOUNT_TYPE_LABELS
admin.templates.env.globals["expense_category_badge_colors"] = (
    EXPENSE_CATEGORY_BADGE_COLORS
)
admin.templates.env.globals["expense_category_labels"] = EXPENSE_CATEGORY_LABELS
admin.add_base_view(DashboardView)
admin.add_base_view(FinanceDashboardView)
admin.add_view(UserAdmin)
admin.add_view(RoleAdmin)
admin.add_view(SubscriptionAdmin)
admin.add_view(VPNConfigAdmin)
admin.add_view(ReferralAdmin)
admin.add_view(PaymentTransactionAdmin)
admin.add_view(PromoCodeAdmin)
admin.add_view(PromoCodeUsageAdmin)
admin.add_view(ExpenseAdmin)

# SQLAdmin монтирует СОБСТВЕННОЕ Starlette-приложение (`admin.admin`) под
# `/admin` со своим `exception_handlers` (по умолчанию — только
# `HTTPException`, см. sqladmin/application.py). Обработчики, зарегистрированные
# выше на внешнем `app`, на него не распространяются: AppError/APIError из
# on_model_delete/on_model_change (VPNConfigAdmin, UserAdmin, SubscriptionAdmin)
# ловит внутренний ServerErrorMiddleware как generic 500 и ПЕРЕБРАСЫВАЕТ
# исключение дальше — оно всплывает через внешние BaseHTTPMiddleware и падает
# с RuntimeError("Caught handled exception, but response already started")
# вместо того, чтобы отдать админу внятный текст ошибки (#290).
admin.admin.add_exception_handler(APIError, api_error_handler)
admin.admin.add_exception_handler(SQLAlchemyError, database_exception_handler)
admin.admin.add_exception_handler(AppError, app_error_handler)
admin.admin.add_exception_handler(Exception, unhandled_exception_handler)


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
    uvicorn.run(
        app="api.main:app",
        host="0.0.0.0",
        port=8089,
        reload=settings_api.core.reload_fast_api,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
