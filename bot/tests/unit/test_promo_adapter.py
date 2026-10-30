import json

import httpx
import pytest

from bot.promo.adapter import PromoAPIAdapter
from bot.promo.schemas import SPromoValidationResult
from shared.enums.promo_enum import PromoDiscountType


@pytest.mark.asyncio
async def test_validate_code_success(api_client):
    async def handler(request: httpx.Request):
        assert request.url.path == "/promo/validate"

        json_data = json.loads(request.content.decode())
        assert json_data == {"code": "SALE10", "base_amount": 100}

        return httpx.Response(
            status_code=200,
            json={
                "promo_code_id": 1,
                "code": "SALE10",
                "discount_type": "percent",
                "discount_value": 10,
                "base_amount": 100,
                "discount_amount": 10,
                "final_amount": 90,
            },
        )

    client = await api_client(handler)
    adapter = PromoAPIAdapter(client)

    result = await adapter.validate_code(code="SALE10", base_amount=100)

    assert isinstance(result, SPromoValidationResult)
    assert result.promo_code_id == 1
    assert result.code == "SALE10"
    assert result.discount_type == PromoDiscountType.PERCENT
    assert result.discount_amount == 10
    assert result.final_amount == 90
