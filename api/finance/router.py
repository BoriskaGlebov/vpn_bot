from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.core.openapi_responses import ADMIN_RESPONSES
from api.finance.dependencies import get_finance_service
from api.finance.schemas import (
    SBreakevenInfo,
    SMonthlyPnL,
    SMonthlyTrend,
    SYearlySummary,
)
from api.finance.services import FinanceService

router = APIRouter(prefix="/finance", tags=["bot", "FINANCE"])


@router.get(
    "/pnl",
    response_model=list[SMonthlyPnL],
    status_code=status.HTTP_200_OK,
    summary="P&L по месяцам",
    description=(
        "Возвращает помесячный P&L (доход, расход, прибыль, маржа) "
        "за указанный год. По умолчанию — текущий год."
    ),
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_pnl(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    service: FinanceService = Depends(get_finance_service),
    session: AsyncSession = Depends(get_session),
) -> list[SMonthlyPnL]:
    """Возвращает P&L по месяцам за год.

    Args:
        year: Год агрегации (по умолчанию текущий).
        service: Сервис финансовой аналитики.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        list[SMonthlyPnL]: P&L по каждому месяцу.

    """
    return await service.get_monthly_pnl(session=session, year=year)


@router.get(
    "/summary",
    response_model=SYearlySummary,
    status_code=status.HTTP_200_OK,
    summary="Годовой финансовый итог",
    description=(
        "Возвращает годовую сводку: доход, расход, прибыль, средний чек, "
        "ARPU, конверсия в платящих."
    ),
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_summary(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    service: FinanceService = Depends(get_finance_service),
    session: AsyncSession = Depends(get_session),
) -> SYearlySummary:
    """Возвращает годовой финансовый итог.

    Args:
        year: Год (по умолчанию текущий).
        service: Сервис финансовой аналитики.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SYearlySummary: Сводка за год.

    """
    return await service.get_yearly_summary(session=session, year=year)


@router.get(
    "/breakeven",
    response_model=SBreakevenInfo,
    status_code=status.HTTP_200_OK,
    summary="Точка безубыточности",
    description="Сколько платежей в месяц нужно для покрытия расходов.",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_breakeven(
    service: FinanceService = Depends(get_finance_service),
    session: AsyncSession = Depends(get_session),
) -> SBreakevenInfo:
    """Возвращает расчёт точки безубыточности.

    Args:
        service: Сервис финансовой аналитики.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SBreakevenInfo: Данные о точке безубыточности.

    """
    return await service.get_breakeven(session=session)


@router.get(
    "/trend",
    response_model=list[SMonthlyTrend],
    status_code=status.HTTP_200_OK,
    summary="Тренд выручки",
    description="MoM-тренд выручки за последние N месяцев (по умолчанию 6).",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_trend(
    months: int = Query(default=6, ge=1, le=24),
    service: FinanceService = Depends(get_finance_service),
    session: AsyncSession = Depends(get_session),
) -> list[SMonthlyTrend]:
    """Возвращает тренд выручки с MoM-изменением.

    Args:
        months: Глубина тренда в месяцах (1–24, по умолчанию 6).
        service: Сервис финансовой аналитики.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        list[SMonthlyTrend]: Список месяцев с выручкой и MoM-%.

    """
    return await service.get_trend(session=session, months=months)
