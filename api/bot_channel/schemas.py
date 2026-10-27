from pydantic import BaseModel, Field

from api.users.schemas import SVPNConfigOut
from shared.enums.vpn_enum import VPNRevokeStatus


class SRevokeConfigRequest(BaseModel):
    """Команда боту: отозвать доступ VPN-конфига на нодах/панелях."""

    tg_id: int = Field(..., description="Telegram ID владельца конфига")
    config: SVPNConfigOut = Field(..., description="Конфиг, доступ которого отзывается")


class SRevokeConfigResponse(BaseModel):
    """Ответ бота на команду отзыва доступа (зеркало `bot.internal.schemas`)."""

    status: VPNRevokeStatus = Field(..., description="Исход отзыва доступа")
    detail: str | None = Field(None, description="Пояснение к исходу")
