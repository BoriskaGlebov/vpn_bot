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


class SBroadcastRequest(BaseModel):
    """Команда боту: разослать текст выбранным получателям."""

    text: str = Field(..., min_length=1, description="Текст рассылки")
    recipients: list[int] = Field(
        ..., min_length=1, description="Telegram ID получателей"
    )


class SBroadcastResponse(BaseModel):
    """Ответ бота на команду рассылки (зеркало `bot.internal.schemas`).

    Рассылка на стороне бота асинхронна — этот ответ лишь подтверждает приём
    команды, итоговый отчёт (доставлено/не доставлено) бот присылает в
    админ-чат отдельным сообщением.
    """

    accepted: bool = Field(..., description="Команда принята к исполнению")
    recipients: int = Field(..., description="Число получателей, принятых к рассылке")
