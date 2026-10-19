from api.referrals.services import ReferralService


def get_referral_service() -> ReferralService:
    """Возвращает экземпляр ReferralService."""
    return ReferralService()
