from datetime import datetime

from fastapi import Request
from sqladmin import BaseView, expose
from sqladmin.templating import _TemplateResponse

from api.admin.badges import EXPENSE_CATEGORY_LABELS
from api.core.config import settings_api
from api.core.database import async_session
from api.expense.dao import ExpenseDAO
from api.finance.services import FinanceService


class FinanceDashboardView(BaseView):
    """Финансовый дашборд: P&L, расходы по категориям, тренды, безубыточность."""

    name = "Финансы"
    icon = "fa-solid fa-coins"

    @expose("/finance-dashboard", methods=["GET"], identity="finance_dashboard")
    async def finance_dashboard(self, request: Request) -> _TemplateResponse:
        """Рендерит страницу финансового дашборда."""
        now = datetime.now(settings_api.core.tzinfo)
        year = now.year
        service = FinanceService()

        async with async_session() as session:
            pnl = await service.get_monthly_pnl(session=session, year=year)
            summary = await service.get_yearly_summary(session=session, year=year)
            breakeven = await service.get_breakeven(session=session)
            trend = await service.get_trend(session=session, months=6)
            expense_by_cat = await ExpenseDAO.get_yearly_by_category(
                session=session,
                year=year,
            )

        current_month_pnl = pnl[-1] if pnl else None
        current_month_rev = current_month_pnl.revenue if current_month_pnl else 0
        current_month_exp = current_month_pnl.expenses if current_month_pnl else 0

        breakeven_pct = (
            round(breakeven.current_monthly_payments / breakeven.payments_needed * 100)
            if breakeven.payments_needed > 0
            else 100
        )

        pnl_months = [p.month for p in pnl]
        pnl_revenue = [p.revenue for p in pnl]
        pnl_expenses = [p.expenses for p in pnl]
        pnl_profit = [p.profit for p in pnl]

        trend_months = [t.month for t in trend]
        trend_revenue = [t.revenue for t in trend]
        trend_mom = [t.mom_pct for t in trend]

        cat_labels = [
            EXPENSE_CATEGORY_LABELS.get(cat, cat) for cat, _ in expense_by_cat
        ]
        cat_values = [total for _, total in expense_by_cat]

        context = {
            "title": "Финансы",
            "year": year,
            "summary": summary,
            "current_month_rev": current_month_rev,
            "current_month_exp": current_month_exp,
            "breakeven": breakeven,
            "breakeven_pct": min(breakeven_pct, 100),
            "pnl_months": pnl_months,
            "pnl_revenue": pnl_revenue,
            "pnl_expenses": pnl_expenses,
            "pnl_profit": pnl_profit,
            "cat_labels": cat_labels,
            "cat_values": cat_values,
            "trend_months": trend_months,
            "trend_revenue": trend_revenue,
            "trend_mom": trend_mom,
        }
        return await self.templates.TemplateResponse(
            request,
            "admin/finance_dashboard.html",
            context,
        )
