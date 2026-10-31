from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import check_admin_role
from api.core.dependencies import get_session
from api.core.openapi_responses import ADMIN_RESPONSES
from api.expense.dependencies import get_expense_service
from api.expense.schemas import (
    SExpenseCreate,
    SExpenseFilter,
    SExpenseRead,
    SExpenseUpdate,
    SMonthlyExpenseSummary,
)
from api.expense.services import ExpenseService
from shared.enums.expense_enum import ExpenseCategory

router = APIRouter(prefix="/expenses", tags=["bot", "EXPENSES"])

_CURRENT_YEAR = date.today().year


@router.post(
    "",
    response_model=SExpenseRead,
    status_code=status.HTTP_201_CREATED,
    summary="Создать расход",
    description="Создаёт новую запись о расходе.",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def create_expense(
    payload: SExpenseCreate,
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> SExpenseRead:
    """Создаёт новую запись о расходе.

    Args:
        payload: Данные нового расхода.
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SExpenseRead: Созданная запись.

    """
    expense = await service.create(session=session, data=payload)
    return SExpenseRead.model_validate(expense)


@router.get(
    "/summary",
    response_model=list[SMonthlyExpenseSummary],
    status_code=status.HTTP_200_OK,
    summary="Сводка расходов по месяцам",
    description=(
        "Возвращает суммарные расходы по месяцам за указанный год. "
        "По умолчанию — текущий год."
    ),
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_expense_summary(
    year: int = Query(default=_CURRENT_YEAR, ge=2000, le=2100),
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> list[SMonthlyExpenseSummary]:
    """Возвращает месячную агрегацию расходов за год.

    Args:
        year: Год агрегации (по умолчанию текущий).
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        list[SMonthlyExpenseSummary]: Список месячных сводок.

    """
    return await service.get_monthly_summary(session=session, year=year)


@router.get(
    "",
    response_model=list[SExpenseRead],
    status_code=status.HTTP_200_OK,
    summary="Список расходов",
    description="Возвращает все расходы, опционально отфильтрованные по категории и/или имени ноды.",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_expenses(
    category: str | None = Query(default=None),
    node_name: str | None = Query(default=None),
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> list[SExpenseRead]:
    """Возвращает список расходов с опциональной фильтрацией.

    Args:
        category: Фильтр по категории расхода.
        node_name: Фильтр по имени VPN-ноды.
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        list[SExpenseRead]: Список записей.

    """
    filters = SExpenseFilter(
        category=ExpenseCategory(category) if category else None,
        node_name=node_name,
    )
    expenses = await service.get_all(session=session, filters=filters)
    return [SExpenseRead.model_validate(e) for e in expenses]


@router.get(
    "/{expense_id}",
    response_model=SExpenseRead,
    status_code=status.HTTP_200_OK,
    summary="Получить расход по ID",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def get_expense(
    expense_id: int,
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> SExpenseRead:
    """Возвращает расход по ID.

    Args:
        expense_id: ID записи.
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SExpenseRead: Найденная запись.

    Raises
        ExpenseNotFoundError: Если запись не найдена.

    """
    expense = await service.get_by_id(session=session, expense_id=expense_id)
    return SExpenseRead.model_validate(expense)


@router.patch(
    "/{expense_id}",
    response_model=SExpenseRead,
    status_code=status.HTTP_200_OK,
    summary="Обновить расход",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def update_expense(
    expense_id: int,
    payload: SExpenseUpdate,
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> SExpenseRead:
    """Частично обновляет запись о расходе (PATCH).

    Args:
        expense_id: ID обновляемой записи.
        payload: Новые значения полей.
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Returns
        SExpenseRead: Обновлённая запись.

    Raises
        ExpenseNotFoundError: Если запись не найдена.

    """
    expense = await service.update(session=session, expense_id=expense_id, data=payload)
    return SExpenseRead.model_validate(expense)


@router.delete(
    "/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить расход",
    responses=ADMIN_RESPONSES,
    dependencies=[Depends(check_admin_role)],
)
async def delete_expense(
    expense_id: int,
    service: ExpenseService = Depends(get_expense_service),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Удаляет запись о расходе.

    Args:
        expense_id: ID удаляемой записи.
        service: Сервис расходов.
        session: Асинхронная SQLAlchemy-сессия.

    Raises
        ExpenseNotFoundError: Если запись не найдена.

    """
    await service.delete(session=session, expense_id=expense_id)
