from api.referrals.services import ReferralService


def get_referral_service() -> ReferralService:
    """Depends для ReferralService."""
    return ReferralService()
