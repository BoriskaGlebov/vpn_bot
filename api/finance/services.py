import math
from datetime import datetime

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.config import settings_api
from api.expense.dao import ExpenseDAO
from api.finance.schemas import (
    SBreakevenInfo,
    SMonthlyPnL,
    SMonthlyTrend,
    SYearlySummary,
)
from api.payment.dao import PaymentTransactionDAO
from api.users.models import User


class FinanceService:
    """Сервис финансовой аналитики: P&L, ARPU, безубыточность, тренды."""

    async def get_monthly_pnl(
        self,
        session: AsyncSession,
        year: int,
    ) -> list[SMonthlyPnL]:
        """P&L по месяцам за указанный год.

        Сопоставляет помесячную выручку (PAID-транзакции) с помесячными
        расходами (Expense.period_start).

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год.

        Returns
            list[SMonthlyPnL]: Список P&L по месяцам, отсортированный
            по возрастанию месяца.

        """
        revenue_rows = await PaymentTransactionDAO.get_monthly_revenue(
            session=session,
            year=year,
        )
        expense_rows = await ExpenseDAO.get_monthly_totals(
            session=session,
            year=year,
        )
        revenue_map = dict(revenue_rows)
        expense_map = dict(expense_rows)
        all_months = sorted(set(revenue_map) | set(expense_map))

        result: list[SMonthlyPnL] = []
        for month in all_months:
            rev = revenue_map.get(month, 0)
            exp = expense_map.get(month, 0)
            profit = rev - exp
            margin = round(profit / rev * 100, 2) if rev else 0.0
            result.append(
                SMonthlyPnL(
                    month=month,
                    revenue=rev,
                    expenses=exp,
                    profit=profit,
                    margin_pct=margin,
                )
            )
        logger.info("[FINANCE] P&L за {} год: {} месяцев", year, len(result))
        return result

    async def get_yearly_summary(
        self,
        session: AsyncSession,
        year: int,
    ) -> SYearlySummary:
        """Годовой финансовый итог: доход, расход, ARPU, средний чек, конверсия.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год.

        Returns
            SYearlySummary: Сводка.

        """
        total_revenue = await PaymentTransactionDAO.get_year_income(
            session=session,
            year=year,
        )
        expense_rows = await ExpenseDAO.get_monthly_totals(
            session=session,
            year=year,
        )
        total_expenses = sum(total for _, total in expense_rows)

        paying_users = await PaymentTransactionDAO.count_paying_users(
            session=session,
            year=year,
        )

        count_result = await session.execute(select(func.count()).select_from(User))
        total_users: int = count_result.scalar_one()

        avg_check = round(total_revenue / paying_users, 2) if paying_users else 0.0
        arpu = round(total_revenue / paying_users, 2) if paying_users else 0.0
        conversion = round(paying_users / total_users * 100, 2) if total_users else 0.0

        summary = SYearlySummary(
            year=year,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            total_profit=total_revenue - total_expenses,
            avg_check=avg_check,
            arpu=arpu,
            paying_users=paying_users,
            total_users=total_users,
            conversion_pct=conversion,
        )
        logger.info("[FINANCE] Годовой итог {}: profit={}", year, summary.total_profit)
        return summary

    async def get_breakeven(self, session: AsyncSession) -> SBreakevenInfo:
        """Точка безубыточности: сколько платежей нужно в месяц.

        Расчёт:
        - monthly_expenses = среднемесячные расходы текущего года
          (сумма расходов / кол-во прошедших месяцев включая текущий).
        - avg_check = годовой доход / кол-во PAID-транзакций.
        - payments_needed = ceil(monthly_expenses / avg_check).
        - current_monthly_payments = кол-во PAID за текущий месяц.

        Args:
            session: Асинхронная SQLAlchemy-сессия.

        Returns
            SBreakevenInfo: Расчёт безубыточности.

        """
        tz = settings_api.core.tzinfo
        now = datetime.now(tz=tz)
        year = now.year
        month = now.month

        expense_rows = await ExpenseDAO.get_monthly_totals(
            session=session,
            year=year,
        )
        total_expenses = sum(total for _, total in expense_rows)
        months_passed = month
        monthly_expenses = total_expenses // months_passed if months_passed else 0

        total_revenue = await PaymentTransactionDAO.get_year_income(
            session=session,
            year=year,
        )
        paying_users = await PaymentTransactionDAO.count_paying_users(
            session=session,
            year=year,
        )
        avg_check = round(total_revenue / paying_users, 2) if paying_users else 0.0

        payments_needed = math.ceil(monthly_expenses / avg_check) if avg_check else 0
        current_payments = await PaymentTransactionDAO.count_monthly_payments(
            session=session,
            year=year,
            month=month,
        )

        info = SBreakevenInfo(
            monthly_expenses=monthly_expenses,
            avg_check=avg_check,
            payments_needed=payments_needed,
            current_monthly_payments=current_payments,
            gap=payments_needed - current_payments,
        )
        logger.info(
            "[FINANCE] Безубыточность: need={} current={} gap={}",
            payments_needed,
            current_payments,
            info.gap,
        )
        return info

    async def get_trend(
        self,
        session: AsyncSession,
        months: int = 6,
    ) -> list[SMonthlyTrend]:
        """Тренд выручки за последние N месяцев с MoM-изменением.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            months: Глубина тренда (по умолчанию 6).

        Returns
            list[SMonthlyTrend]: Список месяцев с выручкой и MoM-%.

        """
        tz = settings_api.core.tzinfo
        now = datetime.now(tz=tz)
        current_year = now.year
        current_month = now.month

        years = {current_year}
        m = current_month - months
        if m <= 0:
            years.add(current_year - 1)

        revenue_map: dict[str, int] = {}
        for yr in sorted(years):
            rows = await PaymentTransactionDAO.get_monthly_revenue(
                session=session,
                year=yr,
            )
            for month_str, total in rows:
                revenue_map[month_str] = total

        all_months: list[str] = []
        y, mo = current_year, current_month
        for _ in range(months + 1):
            all_months.append(f"{y:04d}-{mo:02d}")
            mo -= 1
            if mo == 0:
                mo = 12
                y -= 1
        all_months.reverse()

        result: list[SMonthlyTrend] = []
        for i in range(1, len(all_months)):
            month_str = all_months[i]
            rev = revenue_map.get(month_str, 0)
            prev_rev = revenue_map.get(all_months[i - 1], 0)
            mom: float | None = None
            if prev_rev > 0:
                mom = round((rev - prev_rev) / prev_rev * 100, 2)
            result.append(SMonthlyTrend(month=month_str, revenue=rev, mom_pct=mom))

        logger.info("[FINANCE] Тренд: {} месяцев", len(result))
        return result
