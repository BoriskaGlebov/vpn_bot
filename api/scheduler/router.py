from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.dependencies import get_session
from api.scheduler.dependencies import (
    get_subscription_scheduler_service,
)
from api.scheduler.mapper import map_event, map_stats
from api.scheduler.schemas import CheckAllSubscriptionsResponse
from api.scheduler.services import SubscriptionScheduler

router = APIRouter(prefix="/scheduler", tags=["bot", "SCHEDULER"])


@router.post(
    "/check-all",
    response_model=CheckAllSubscriptionsResponse,
    summary="Проверка подписок пользователей",
    description=(
        "Запускает проверку всех пользователей и их подписок.\n\n"
        "В процессе выполнения:\n"
        "- деактивирует истёкшие подписки\n"
        "- удаляет VPN-конфигурации при необходимости\n"
        "- проверяет превышение лимитов устройств\n"
        "- формирует список событий для дальнейшей обработки (бот, внешние сервисы)\n\n"
        "Возвращает агрегированную статистику и список событий."
    ),
    response_description=(
        "Статистика обработки и список событий для последующей обработки "
        "(уведомления пользователей, удаление конфигураций и т.д.)"
    ),
)
async def check_all(
    session: AsyncSession = Depends(get_session),
    service: SubscriptionScheduler = Depends(get_subscription_scheduler_service),
) -> CheckAllSubscriptionsResponse:
    """Проверяет подписки всех пользователей и формирует события.

    Функция инициирует процесс проверки подписок пользователей через
    `SubscriptionScheduler`. В ходе выполнения производится анализ состояния
    подписок и генерация событий, которые могут быть обработаны внешними
    системами (например, Telegram-ботом или сервисом управления конфигурациями).

    Args:
        session: Асинхронная сессия базы данных SQLAlchemy.
        service: Сервис обработки подписок, инкапсулирующий бизнес-логику.

    Returns
        CheckAllSubscriptionsResponse: Объект ответа, содержащий:
            - stats: агрегированную статистику обработки пользователей
            - events: список событий для последующей обработки

    Notes
        - Метод не выполняет отправку уведомлений или удаление файлов напрямую.
        - Все действия описываются через события, которые должны быть обработаны
          отдельными компонентами системы.
        - Используется как точка интеграции с ботом или внешними сервисами.

    Raises
        HTTPException: В случае ошибок на уровне зависимостей или обработки запроса.

    """
    stats, events = await service.check_all_subscriptions(
        session=session,
    )
    return CheckAllSubscriptionsResponse(
        stats=map_stats(stats),
        events=[map_event(e) for e in events],
    )
