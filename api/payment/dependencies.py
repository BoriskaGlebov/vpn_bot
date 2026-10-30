from fastapi import Depends

from api.payment.services import PaymentService
from api.promo.dependencies import get_promo_service
from api.promo.services import PromoService
from api.referrals.dependencies import get_referral_service
from api.referrals.services import ReferralService
from api.subscription.dependencies import get_subscription_service
from api.subscription.services import SubscriptionService


def get_payment_service(
    sub_service: SubscriptionService = Depends(get_subscription_service),
    ref_service: ReferralService = Depends(get_referral_service),
    promo_service: PromoService = Depends(get_promo_service),
) -> PaymentService:
    """Создаёт экземпляр PaymentService.

    Args:
        sub_service:
            Сервис управления подписками.

        ref_service:
            Сервис реферальной системы.

        promo_service:
            Сервис промокодов.

    Returns
        PaymentService: Сервис платежей.

    """
    return PaymentService(
        sub_service=sub_service,
        ref_service=ref_service,
        promo_service=promo_service,
    )
