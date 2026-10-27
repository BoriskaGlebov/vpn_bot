import httpx
from loguru import logger
from pydantic import ValidationError

from api.app_error.base_error import BotChannelUnavailableError, VPNRevokeFailedError
from api.bot_channel.schemas import SRevokeConfigRequest, SRevokeConfigResponse
from api.core.config import BotChannelSettings
from api.users.schemas import SVPNConfigOut
from shared.enums.vpn_enum import VPNRevokeStatus


class BotChannelClient:
    """Клиент внутреннего канала api → bot.

    api/ — единственный, кто ходит в Postgres, а к VPN-панелям/нодам ходит
    только bot/. Поэтому команды, которым нужны действия на нодах, api
    отправляет боту по HTTP (`bot/internal/router.py`, авторизация X-API-Key).

    Повторных попыток нет намеренно: вызов инициирует администратор вручную,
    а недоступность бота должна сразу стать видимой ошибкой, а не зависанием
    запроса в админке.

    Args:
        settings: Настройки канала (адрес бота, ключ, таймауты).
        transport: Транспорт httpx; подменяется в тестах.

    """

    def __init__(
        self,
        settings: BotChannelSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._base_url = f"http://{settings.url}:{settings.port}"
        self._timeout = httpx.Timeout(
            connect=settings.connect_timeout,
            read=settings.timeout,
            write=settings.timeout,
            pool=settings.timeout,
        )
        self._transport = transport

    async def revoke_config(self, tg_id: int, config: SVPNConfigOut) -> VPNRevokeStatus:
        """Просит бота отозвать доступ конфига на нодах/панелях.

        Контракт для вызывающего кода: если метод вернул значение — запись
        конфига в БД можно удалять (`OK` — удалён на ноде, `NOT_FOUND` — на
        нодах его уже нет). Любое исключение означает «отзыв не подтверждён»,
        запись в БД удалять нельзя.

        Args:
            tg_id: Telegram ID владельца конфига.
            config: Конфиг, доступ которого отзывается.

        Returns
            VPNRevokeStatus: `OK` или `NOT_FOUND`.

        Raises
            BotChannelUnavailableError: Бот недоступен, канал не настроен,
                ответ не-2xx (в т.ч. 401/403) или тело нераспознаваемо.
            VPNRevokeFailedError: Бот ответил `node_error` — нода/панель
                не смогла удалить конфиг.

        """
        api_key = self._settings.api_key.get_secret_value()
        if not api_key:
            logger.error(
                "Канал api → bot не настроен: BOT_INTERNAL_API_KEY пуст, "
                "отзыв конфига {} не отправлен",
                config.file_name,
            )
            raise BotChannelUnavailableError("не задан BOT_INTERNAL_API_KEY")

        logger.info(
            "Отправляю боту запрос на отзыв конфига {} (tg_id={})",
            config.file_name,
            tg_id,
        )
        request = SRevokeConfigRequest(tg_id=tg_id, config=config)
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    "/internal/vpn/revoke",
                    json=request.model_dump(mode="json"),
                    headers={"X-API-Key": api_key},
                )
        except httpx.TimeoutException as exc:
            logger.error("Таймаут ответа бота при отзыве конфига {}", config.file_name)
            raise BotChannelUnavailableError("таймаут ответа", cause=exc) from exc
        except httpx.RequestError as exc:
            logger.error(
                "Бот недоступен при отзыве конфига {}: {}", config.file_name, exc
            )
            raise BotChannelUnavailableError("нет соединения", cause=exc) from exc

        if response.status_code != httpx.codes.OK:
            logger.error(
                "Бот ответил {} на отзыв конфига {}",
                response.status_code,
                config.file_name,
            )
            raise BotChannelUnavailableError(f"HTTP {response.status_code}")

        try:
            result = SRevokeConfigResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            logger.error("Нераспознаваемый ответ бота на отзыв {}", config.file_name)
            raise BotChannelUnavailableError(
                "нераспознаваемый ответ", cause=exc
            ) from exc

        if result.status == VPNRevokeStatus.NODE_ERROR:
            # Расхождение БД и нод: конфиг мог остаться на сервере, а запись
            # в БД намеренно сохраняем — громко логируем, не молчим.
            logger.error(
                "Расхождение: нода не отозвала конфиг {} (tg_id={}), запись в БД "
                "сохранена. Бот: {}",
                config.file_name,
                tg_id,
                result.detail,
            )
            raise VPNRevokeFailedError(config.file_name, result.detail)

        logger.info(
            "Бот подтвердил отзыв конфига {} (tg_id={}): статус={} — можно удалять "
            "запись в БД",
            config.file_name,
            tg_id,
            result.status,
        )
        return result.status
