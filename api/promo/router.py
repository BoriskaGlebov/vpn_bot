from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.dependencies import get_current_user, get_session
from api.core.openapi_responses import AUTH_RESPONSES
from api.promo.dependencies import get_promo_service
from api.promo.schemas import SPromoValidateIn, SPromoValidationResult
from api.promo.services import PromoService
from api.users.models import User

router = APIRouter(prefix="/promo", tags=["bot", "PROMO"])


@router.post(
    "/validate",
    response_model=SPromoValidationResult,
    status_code=status.HTTP_200_OK,
    summary="Проверка промокода",
    description=(
        "Проверяет применимость промокода для текущего пользователя и "
        "считает скидку от переданной базовой суммы. Не резервирует "
        "применение — только расчёт для предпросмотра перед оплатой."
    ),
    responses=AUTH_RESPONSES,
)
async def validate_promo_code(
    payload: SPromoValidateIn,
    service: PromoService = Depends(get_promo_service),
    user_auth: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SPromoValidationResult:
    """Проверяет промокод и считает скидку для текущего пользователя.

    Args:
        payload: Код промокода и базовая сумма подписки.
        service: Сервис промокодов.
        user_auth: Авторизованный пользователь.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SPromoValidationResult: Данные промокода и рассчитанная скидка.

    Raises
        PromoCodeNotFoundError: Код с таким значением не существует.
        PromoCodeInactiveError: Код деактивирован либо вне срока действия.
        PromoCodeLimitReachedError: Лимит применений исчерпан.
        PromoCodeAlreadyUsedError: Этот пользователь уже применял код.

    """
    return await service.validate_code(
        session=session,
        code=payload.code,
        user_id=user_auth.id,
        base_amount=payload.base_amount,
    )
