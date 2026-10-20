"""#281: единственный SubscriptionStats (бот-дубликат удалён, он не суммировал checked)."""

from api.scheduler.domain.stats import SubscriptionStats


def test_add_sums_every_field():
    total = SubscriptionStats(checked=1, expired=2, configs_deleted=3)
    other = SubscriptionStats(checked=10, expired=20, configs_deleted=30)

    total.add(other)

    assert total.checked == 11
    assert total.expired == 22
    assert total.configs_deleted == 33
