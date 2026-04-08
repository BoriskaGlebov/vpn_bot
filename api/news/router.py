from fastapi import APIRouter, Depends
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.news.dependencies import get_news_service
from api.news.services import NewsService
from api.users.models import User

router = APIRouter(prefix="/news", tags=["bot", "news"])


@router.get(
    "/recipients",
    response_model=list[int],
    summary="Получить список получателей рассылки",
    description=(
        "Возвращает список Telegram ID пользователей, которым разрешена "
        "новостная рассылка.\n\n"
        "Из выборки исключаются пользователи с административной ролью."
    ),
    response_description="Список Telegram ID пользователей",
)
async def get_news_recipients(
    session: AsyncSession = Depends(get_session),
    service: NewsService = Depends(get_news_service),
    admin_auth: User = Depends(check_admin_role),
) -> list[int]:
    """Получает список Telegram ID пользователей для новостной рассылки.

    Endpoint используется ботом или внутренними сервисами для получения
    актуального списка получателей уведомлений.

    В выборку включаются все пользователи, кроме имеющих роль администратора.

    Args:
        session (AsyncSession): Асинхронная сессия базы данных.
        service (NewsService): Сервис для работы с новостной рассылкой.
        admin_auth: Проверка, что пользователь админ.

    Returns
        list[int]: Список Telegram ID пользователей.

    Raises
        HTTPException: В случае ошибок при получении данных (например, проблемы с БД).

    """
    recipients = await service.get_users_for_news(session=session)
    logger.info(
        "Получено {count} пользователей для новостной рассылки",
        count=len(recipients),
    )
    return recipients
