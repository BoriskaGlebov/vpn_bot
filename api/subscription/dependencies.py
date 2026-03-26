from api.subscription.services import SubscriptionService


def get_subscription_service() -> SubscriptionService:
    """Depends для SubscriptionService."""
    return SubscriptionService()
