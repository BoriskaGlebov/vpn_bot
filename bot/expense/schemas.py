from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from shared.enums.expense_enum import ExpenseCategory


class SYearlySummary(BaseModel):
    """Годовой финансовый итог (зеркало api/finance/schemas.py)."""

    year: int
    total_revenue: int
    total_expenses: int
    total_profit: int
    avg_check: float
    arpu: float
    paying_users: int
    total_users: int
    conversion_pct: float


class SExpenseCreate(BaseModel):
    """Данные для создания расхода (зеркало api/expense/schemas.py)."""

    amount: int = Field(..., gt=0)
    category: ExpenseCategory
    description: str | None = None
    period_start: date
    period_end: date | None = None
    node_name: str | None = Field(None, max_length=64)
    is_recurring: bool = True


class SExpenseRead(BaseModel):
    """Созданный расход (ответ API)."""

    id: int
    amount: int
    category: ExpenseCategory
    description: str | None
    period_start: date
    period_end: date | None
    node_name: str | None
    is_recurring: bool
    created_at: datetime
    updated_at: datetime
