from pydantic import BaseModel, Field

from shared.enums.promo_enum import PromoDiscountType


class SPromoValidateIn(BaseModel):
    """Данные для проверки промокода перед оформлением подписки.

    Attributes
        code (str): Код промокода, введённый пользователем.
        base_amount (int): Базовая цена подписки (до скидки).

    """

    code: str = Field(..., min_length=1, max_length=32)
    base_amount: int = Field(..., gt=0)


class SPromoValidationResult(BaseModel):
    """Результат проверки промокода.

    Attributes
        promo_code_id (int): ID промокода в БД.
        code (str): Код промокода.
        discount_type (PromoDiscountType): Тип скидки.
        discount_value (int): Величина скидки (процент либо рубли).
        base_amount (int): Сумма до применения скидки.
        discount_amount (int): Сумма скидки в рублях.
        final_amount (int): Итоговая сумма к оплате.

    """

    promo_code_id: int
    code: str
    discount_type: PromoDiscountType
    discount_value: int
    base_amount: int
    discount_amount: int
    final_amount: int
