from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from shared.enums.promo_enum import PromoDiscountType


class SPromoCodeFilter(BaseModel):
    """Фильтр поиска промокода по коду.

    Attributes
        code (str): Код промокода (регистр уже нормализован вызывающей
            стороной).

    """

    code: str
    model_config = ConfigDict(from_attributes=True)


class SPromoValidationResult(BaseModel):
    """Результат проверки промокода для конкретного пользователя и суммы.

    Attributes
        promo_code_id (int): ID промокода в БД.
        code (str): Код промокода.
        discount_type (PromoDiscountType): Тип скидки.
        discount_value (int): Величина скидки (процент либо рубли).
        base_amount (int): Сумма до применения скидки.
        discount_amount (int): Сумма скидки в рублях.
        final_amount (int): Итоговая сумма к оплате (не менее 1 рубля).

    """

    promo_code_id: int
    code: str
    discount_type: PromoDiscountType
    discount_value: int
    base_amount: int
    discount_amount: int
    final_amount: int


class SPromoCodeUsageCreate(BaseModel):
    """Данные для фиксации применения промокода.

    Attributes
        promo_code_id (int): Применённый промокод.
        user_id (int): Пользователь, применивший код.
        transaction_id: Транзакция, к которой применён код.
        discount_amount (int): Сумма предоставленной скидки.
        used_at (datetime): Момент подтверждённого применения.

    """

    promo_code_id: int
    user_id: int
    transaction_id: UUID
    discount_amount: int
    used_at: datetime


class SPromoUsageFilter(BaseModel):
    """Фильтр поиска применения промокода конкретным пользователем."""

    promo_code_id: int
    user_id: int


class SPromoCodeOut(BaseModel):
    """Публичные данные промокода (для отображения в боте)."""

    id: int
    code: str
    discount_type: PromoDiscountType
    discount_value: int
    max_uses: int | None
    used_count: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    model_config = ConfigDict(from_attributes=True)


class SPromoValidateIn(BaseModel):
    """Входные данные для проверки промокода.

    Attributes
        code (str): Код промокода, введённый пользователем.
        base_amount (int): Базовая цена подписки (до скидки), от которой
            считается скидка.

    """

    code: str = Field(..., min_length=1, max_length=32)
    base_amount: int = Field(..., gt=0)
