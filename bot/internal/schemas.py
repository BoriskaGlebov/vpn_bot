from pydantic import BaseModel, Field

from bot.users.schemas import SVPNConfigOut
from shared.enums.vpn_enum import VPNRevokeStatus


class SRevokeConfigRequest(BaseModel):
    """Команда api → bot: отозвать доступ VPN-конфига на нодах/панелях."""

    tg_id: int = Field(..., description="Telegram ID владельца конфига")
    config: SVPNConfigOut = Field(..., description="Конфиг, доступ которого отзывается")


class SRevokeConfigResponse(BaseModel):
    """Результат отзыва доступа конфига.

    Attributes
        status: Исход операции (см. `VPNRevokeStatus`).
        detail: Человекочитаемое пояснение (для логов api/), необязательно.

    """

    status: VPNRevokeStatus = Field(..., description="Исход отзыва доступа")
    detail: str | None = Field(None, description="Пояснение к исходу")
