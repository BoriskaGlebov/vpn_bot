from datetime import datetime, timedelta

from fastapi import Request
from sqladmin import BaseView, expose
from sqladmin.templating import _TemplateResponse
from sqlalchemy import func, or_, select

from api.core.config import settings_api
from api.core.database import async_session
from api.payment.model import PaymentTransaction
from api.promo.models import PromoCode, PromoCodeUsage
from api.referrals.models import Referral
from api.subscription.models import Subscription, SubscriptionType
from api.users.models import User
from api.vpn.models import VPNConfig
from shared.enums.payment_enum import PaymentStatus


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
        """Рендерит страницу дашборда."""
        now = datetime.now(settings_api.core.tzinfo)
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        async with async_session() as session:
            users_total = await session.scalar(select(func.count(User.id))) or 0
            users_new_7d = (
                await session.scalar(
                    select(func.count(User.id)).where(User.created_at >= week_ago)
                )
                or 0
            )
            users_new_30d = (
                await session.scalar(
                    select(func.count(User.id)).where(User.created_at >= month_ago)
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
                        PaymentTransaction.paid_at >= month_ago,
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

            # "Активен" = прошёл бы PromoService.validate_code по дате/лимиту
            # (без проверки конкретного пользователя) — не просто is_active,
            # иначе в списке висели бы коды, которые на самом деле уже не
            # применить (истёк срок или исчерпан лимит).
            active_promo_codes = (
                await session.scalars(
                    select(PromoCode)
                    .where(
                        PromoCode.is_active.is_(True),
                        or_(
                            PromoCode.valid_from.is_(None),
                            PromoCode.valid_from <= now,
                        ),
                        or_(
                            PromoCode.valid_until.is_(None),
                            PromoCode.valid_until >= now,
                        ),
                        or_(
                            PromoCode.max_uses.is_(None),
                            PromoCode.used_count < PromoCode.max_uses,
                        ),
                    )
                    .order_by(PromoCode.created_at.desc())
                )
            ).all()

            promo_usages_total = (
                await session.scalar(select(func.count(PromoCodeUsage.id))) or 0
            )
            promo_discount_total = (
                await session.scalar(
                    select(func.coalesce(func.sum(PromoCodeUsage.discount_amount), 0))
                )
                or 0
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
            "active_promo_codes": active_promo_codes,
            "promo_usages_total": promo_usages_total,
            "promo_discount_total": promo_discount_total,
        }
        return await self.templates.TemplateResponse(
            request, "admin/dashboard.html", context
        )
