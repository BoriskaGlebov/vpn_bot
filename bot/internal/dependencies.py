import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from bot.core.config import settings_bot
from bot.core.container import Container
from bot.vpn.services import VPNService

api_key_header = APIKeyHeader(
    name="X-API-Key", scheme_name="InternalApiKeyHeader", auto_error=False
)


def verify_internal_api_key(api_key: str | None = Depends(api_key_header)) -> None:
    """Проверяет ключ внутреннего канала api → bot (заголовок `X-API-Key`).

    Закрыто по умолчанию: если `BOT_INTERNAL_API_KEY` не задан, канал считается
    выключенным и отклоняет любые запросы. Ключ сравнивается в постоянное
    время (`secrets.compare_digest`).

    Args:
        api_key: Значение заголовка `X-API-Key`.

    Raises
        HTTPException: 403, если канал выключен (ключ не сконфигурирован);
            401, если заголовок отсутствует или ключ неверен.

    """
    expected = settings_bot.bot.internal_api_key.get_secret_value()

    if not expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Внутренний канал api → bot отключён",
        )

    if not api_key or not secrets.compare_digest(api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или отсутствующий X-API-Key",
        )


def get_vpn_service(request: Request) -> VPNService:
    """Возвращает `VPNService` из DI-контейнера приложения.

    Контейнер лежит в `app.state.container` (см. `bot/main.py`), как и для
    payment-роутера — так нет циклического импорта `bot.main`.

    Args:
        request: Текущий HTTP-запрос.

    Returns
        VPNService: Сервис VPN из контейнера.

    """
    container: Container = request.app.state.container
    return container.vpn_service
