from api.scheduler.services import SubscriptionScheduler


def get_subscription_scheduler_service() -> SubscriptionScheduler:
    """Depends для SubscriptionScheduler."""
    return SubscriptionScheduler()
