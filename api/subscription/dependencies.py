from api.subscription.services import SubscriptionService, SubscriptionScheduler


def get_subscription_service() -> SubscriptionService:
    """Depends для SubscriptionService."""
    return SubscriptionService()


def get_subscription_scheduler_service()->SubscriptionScheduler:
    """Depends для SubscriptionScheduler."""
    return SubscriptionScheduler()
