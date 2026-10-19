from api.scheduler.services import SubscriptionScheduler


def get_subscription_scheduler_service() -> SubscriptionScheduler:
    """Возвращает экземпляр SubscriptionScheduler."""
    return SubscriptionScheduler()
