from enum import StrEnum


class PromoDiscountType(StrEnum):
    """Тип скидки промокода.

    Attributes
        PERCENT: Скидка в процентах от базовой цены подписки.
        FIXED: Скидка фиксированной суммой в рублях.

    """

    PERCENT = "percent"
    FIXED = "fixed"
