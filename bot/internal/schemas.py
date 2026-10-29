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


class SBroadcastRequest(BaseModel):
    """Команда api → bot: разослать текст выбранным получателям."""

    text: str = Field(..., min_length=1, description="Текст рассылки")
    recipients: list[int] = Field(
        ..., min_length=1, description="Telegram ID получателей"
    )


class SBroadcastResponse(BaseModel):
    """Подтверждение приёма команды на рассылку.

    Сама рассылка асинхронна (запускается в фоне) — итоговый отчёт
    (доставлено/не доставлено) бот присылает в админ-чат отдельным
    сообщением (`BroadcastService._format_broadcast_summary`).
    """

    accepted: bool = Field(..., description="Команда принята к исполнению")
    recipients: int = Field(..., description="Число получателей, принятых к рассылке")
