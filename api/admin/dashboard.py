from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqladmin import BaseView, expose
from sqladmin.templating import _TemplateResponse
from sqlalchemy import func, select

from api.core.database import async_session
from api.payment.model import PaymentStatus, PaymentTransaction
from api.referrals.models import Referral
from api.subscription.models import Subscription, SubscriptionType
from api.users.models import User
from api.vpn.models import VPNConfig


class DashboardView(BaseView):
    """Дашборд с ключевыми метриками сервиса.

    Отдельная страница в SQLAdmin (не привязана к конкретной модели),
    собирающая агрегаты по пользователям, подпискам, платежам и рефералам
    одним набором запросов — без захода в каждую вкладку по отдельности.
    """

    name = "Дашборд"
    icon = "fa-solid fa-chart-line"

    @expose("/dashboard", methods=["GET"], identity="dashboard")
    async def dashboard(self, request: Request) -> _TemplateResponse:
        """Собирает метрики и рендерит страницу дашборда."""
        # Subscription.start_date/end_date хранятся как TIMESTAMPTZ (aware),
        # а User.created_at и PaymentTransaction.paid_at — как TIMESTAMP
        # WITHOUT TIME ZONE (naive), поэтому для сравнения нужны обе версии.
        now = datetime.now(UTC)
        now_naive = now.replace(tzinfo=None)
        week_ago_naive = now_naive - timedelta(days=7)
        month_ago_naive = now_naive - timedelta(days=30)

        async with async_session() as session:
            users_total = await session.scalar(select(func.count(User.id))) or 0
            users_new_7d = (
                await session.scalar(
                    select(func.count(User.id)).where(
                        User.created_at >= week_ago_naive
                    )
                )
                or 0
            )
            users_new_30d = (
                await session.scalar(
                    select(func.count(User.id)).where(
                        User.created_at >= month_ago_naive
                    )
                )
                or 0
            )

            subs_by_type: dict[SubscriptionType, int] = {
                row[0]: row[1]
                for row in (
                    await session.execute(
                        select(Subscription.type, func.count(Subscription.id))
                        .where(Subscription.is_active.is_(True))
                        .group_by(Subscription.type)
                    )
                ).all()
            }

            subs_expiring_7d = (
                await session.scalar(
                    select(func.count(Subscription.id)).where(
                        Subscription.is_active.is_(True),
                        Subscription.end_date.is_not(None),
                        Subscription.end_date <= now + timedelta(days=7),
                        Subscription.end_date >= now,
                    )
                )
                or 0
            )

            revenue_total = (
                await session.scalar(
                    select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
                        PaymentTransaction.status == PaymentStatus.PAID
                    )
                )
                or 0
            )
            revenue_30d = (
                await session.scalar(
                    select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(
                        PaymentTransaction.status == PaymentStatus.PAID,
                        PaymentTransaction.paid_at >= month_ago_naive,
                    )
                )
                or 0
            )

            payments_by_status: dict[PaymentStatus, int] = {
                row[0]: row[1]
                for row in (
                    await session.execute(
                        select(
                            PaymentTransaction.status, func.count(PaymentTransaction.id)
                        ).group_by(PaymentTransaction.status)
                    )
                ).all()
            }

            recent_payments = (
                await session.scalars(
                    select(PaymentTransaction)
                    .order_by(PaymentTransaction.created_at.desc())
                    .limit(10)
                )
            ).all()

            vpn_configs_total = (
                await session.scalar(select(func.count(VPNConfig.id))) or 0
            )

            referrals_total = await session.scalar(select(func.count(Referral.id))) or 0
            referrals_paid = (
                await session.scalar(
                    select(func.count(Referral.id)).where(
                        Referral.bonus_given.is_(True)
                    )
                )
                or 0
            )
            conversion = (
                referrals_paid / referrals_total * 100 if referrals_total else 0.0
            )

        context = {
            "title": "Дашборд",
            "users_total": users_total,
            "users_new_7d": users_new_7d,
            "users_new_30d": users_new_30d,
            "subs_by_type": subs_by_type,
            "subs_expiring_7d": subs_expiring_7d,
            "revenue_total": revenue_total,
            "revenue_30d": revenue_30d,
            "payments_by_status": payments_by_status,
            "recent_payments": recent_payments,
            "vpn_configs_total": vpn_configs_total,
            "referrals_total": referrals_total,
            "referrals_paid": referrals_paid,
            "conversion": conversion,
        }
        return await self.templates.TemplateResponse(
            request, "admin/dashboard.html", context
        )
