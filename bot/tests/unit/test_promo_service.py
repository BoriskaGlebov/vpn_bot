from unittest.mock import AsyncMock

import pytest

from bot.promo.schemas import SPromoValidationResult
from bot.promo.services import PromoService
from shared.enums.promo_enum import PromoDiscountType


@pytest.mark.asyncio
async def test_validate_code_delegates_to_adapter():
    """Сервис — тонкая обёртка над адаптером, без побочной логики."""
    adapter = AsyncMock()
    expected = SPromoValidationResult(
        promo_code_id=1,
        code="SALE10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        base_amount=100,
        discount_amount=10,
        final_amount=90,
    )
    adapter.validate_code.return_value = expected

    service = PromoService(adapter=adapter)
    result = await service.validate_code(code="sale10", base_amount=100)

    adapter.validate_code.assert_awaited_once_with(code="sale10", base_amount=100)
    assert result is expected
