from pydantic import BaseModel


class SMonthlyPnL(BaseModel):
    """P&L за один месяц.

    Attributes
        month: Месяц в формате 'YYYY-MM'.
        revenue: Выручка за месяц в рублях.
        expenses: Расходы за месяц в рублях.
        profit: Прибыль (revenue - expenses).
        margin_pct: Маржинальность (profit / revenue * 100). 0.0 если выручка = 0.

    """

    month: str
    revenue: int
    expenses: int
    profit: int
    margin_pct: float


class SYearlySummary(BaseModel):
    """Годовой финансовый итог.

    Attributes
        year: Год.
        total_revenue: Общая выручка в рублях.
        total_expenses: Общие расходы в рублях.
        total_profit: Прибыль в рублях.
        avg_check: Средний чек PAID-транзакций.
        arpu: Выручка / кол-во уникальных плательщиков.
        paying_users: Кол-во уникальных плательщиков.
        total_users: Общее кол-во пользователей.
        conversion_pct: paying_users / total_users * 100.

    """

    year: int
    total_revenue: int
    total_expenses: int
    total_profit: int
    avg_check: float
    arpu: float
    paying_users: int
    total_users: int
    conversion_pct: float


class SBreakevenInfo(BaseModel):
    """Точка безубыточности.

    Attributes
        monthly_expenses: Средние ежемесячные расходы (текущий год).
        avg_check: Средний чек PAID-платежей (текущий год).
        payments_needed: ceil(monthly_expenses / avg_check) — сколько нужно платежей в месяц.
        current_monthly_payments: Фактическое кол-во платежей за текущий месяц.
        gap: payments_needed - current_monthly_payments (отрицательное = запас).

    """

    monthly_expenses: int
    avg_check: float
    payments_needed: int
    current_monthly_payments: int
    gap: int


class SMonthlyTrend(BaseModel):
    """Выручка за один месяц в тренде.

    Attributes
        month: Месяц 'YYYY-MM'.
        revenue: Выручка в рублях.
        mom_pct: Изменение к предыдущему месяцу (%). None для первого месяца.

    """

    month: str
    revenue: int
    mom_pct: float | None
