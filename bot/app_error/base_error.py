from typing import Any

from bot.app_error.schema import ErrorDetail, ErrorEnvelope


class AppError(Exception):
    """Базовое доменное исключение.

    Все пользовательские исключения приложения должны наследоваться
    от этого класса. Предоставляет единый формат представления ошибки
    и возможность преобразования в :class:`ErrorEnvelope`.

    Attributes
        code: Машиночитаемый код ошибки.
        status_code: HTTP-статус, соответствующий ошибке.
        message: Человекочитаемое описание ошибки.
        details: Дополнительная диагностическая информация.
        cause: Исходное исключение, если оно известно.

    Args:
        message: Описание ошибки.
        details: Дополнительные данные об ошибке.
        cause: Исходное исключение.

    """

    code: str = "app_error"
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(f"[{self.code}] {message}")

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_envelope(self) -> ErrorEnvelope:
        """Преобразует исключение в стандартную структуру ошибки API.

        Returns
            Объект ``ErrorEnvelope`` с информацией о текущей ошибке.

        """
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details,
            )
        )


class MessageNotFoundError(AppError):
    """Ошибка сообщения для редактирования не найдено."""

    code: str = "message_not_found"
    status_code: int = 404

    def __init__(self) -> None:
        super().__init__(message="Сообщение для редактирования не найдено")


class UserNotFoundError(AppError):
    """Пользователь не найден."""

    code = "user_not_found"
    status_code = 404

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"Пользователь с Telegram ID {tg_id} не найден",
            details={"tg_id": tg_id},
        )
        self.tg_id = tg_id


class SubscriptionNotFoundError(AppError):
    """Данные о подписке не найдены."""

    code = "subscription_not_found"
    status_code = 404

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"У пользователя {tg_id} нет активной подписки",
            details={"tg_id": tg_id},
        )
        self.tg_id = tg_id


class VPNLimitError(AppError):
    """Пользователь достиг лимита по количеству конфиг файлов."""

    code = "vpn_limit_reached"
    status_code = 429

    def __init__(self, tg_id: int, limit: int, username: str = "") -> None:
        super().__init__(
            message=f"Пользователь достиг лимита VPN-конфигов ({limit})",
            details={
                "tg_id": tg_id,
                "limit": limit,
                "username": username,
            },
        )

        self.tg_id = tg_id
        self.limit = limit
        self.username = username


class TelegramIdNotProvidedError(AppError):
    """Ошибка отсутствия TelegramID в callback."""

    code = "telegram_id_not_provided"
    status_code = 400

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message=message or "В callback отсутствует telegram_id",
        )


class DeviceMediaMismatchError(AppError):
    """Ошибка несоответствия медиафайлов и фраз в инструкции."""

    code = "device_media_mismatch"
    status_code = 500

    def __init__(self, device: str, media_len: int, messages_len: int) -> None:
        super().__init__(
            message=f"{device}: media ({media_len}) != messages ({messages_len})",
            details={
                "media_len": media_len,
                "messages_len": messages_len,
            },
        )


class DeviceEmptyMessagesError(AppError):
    """Ошибка пустой список инструкций."""

    code = "device_empty_messages"
    status_code = 500

    def __init__(self, device: str) -> None:
        super().__init__(
            message=f"{device}: пустой список инструкций",
            details={"device": device},
        )


class DeviceEmptyMediaError(AppError):
    """Ошибка пустой медиа к инструкции."""

    code = "device_empty_media"
    status_code = 500

    def __init__(self, device: str) -> None:
        super().__init__(
            message=f"{device}: нет файлов в S3",
            details={"device": device},
        )


class DeviceInstructionMismatchError(AppError):
    """Ошибка несоответствия количества инструкций и медиафайлов устройства."""

    code = "device_instruction_mismatch"
    status_code = 500

    def __init__(self, device: str, media: int, messages: int) -> None:
        super().__init__(
            message=(
                f"{device}: несоответствие длин media({media}) и messages({messages})."
                "Ожидается: вступление + подписи ко всем фото (+ опционально финал)"
            ),
            details={
                "media": media,
                "messages": messages,
            },
        )


class VPNNodeNotFoundError(AppError):
    """VPN-нода с указанным именем отсутствует в настройках."""

    code = "vpn_node_not_found"
    status_code = 404

    def __init__(self, name: str) -> None:
        super().__init__(
            message=f"VPN node '{name}' не найден в настройках.",
            details={"name": name},
        )
        self.name = name


class XRayNotConfiguredError(AppError):
    """Для VPN-ноды не настроен XRay."""

    code = "xray_not_configured"
    status_code = 503

    def __init__(self, host: str) -> None:
        super().__init__(
            message=f"XRay не настроен для {host}",
            details={"host": host},
        )
        self.host = host


class ProxyNotConfiguredError(AppError):
    """Для VPN-ноды не настроен Proxy."""

    code = "proxy_not_configured"
    status_code = 503

    def __init__(self, host: str) -> None:
        super().__init__(
            message=f"Proxy не настроен для {host}",
            details={"host": host},
        )
        self.host = host


class NewsRecipientsFetchError(AppError):
    """Не удалось получить список получателей новостной рассылки."""

    code = "news_recipients_fetch_error"
    status_code = 502

    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Не удалось получить список получателей рассылки: {reason}",
            details={"reason": reason},
        )


class TransactionIdMissingError(AppError):
    """В callback-данных отсутствует идентификатор платёжной транзакции."""

    code = "transaction_id_missing"
    status_code = 400

    def __init__(self) -> None:
        super().__init__(message="Отсутствует идентификатор транзакции.")


class SubscriptionActivationFailedError(AppError):
    """После подтверждения оплаты не удалось получить активную подписку пользователя."""

    code = "subscription_activation_failed"
    status_code = 502

    def __init__(self, tg_id: int, reason: str) -> None:
        super().__init__(
            message=f"Не удалось активировать подписку пользователя {tg_id}: {reason}",
            details={"tg_id": tg_id, "reason": reason},
        )
        self.tg_id = tg_id


class PaymentLinkMissingError(AppError):
    """Пользователь выбрал оплату картой, но ссылка на оплату отсутствует.

    Не должно происходить в норме: кнопка "Оплата картой" показывается
    только когда платёжный шлюз вернул ссылку при создании транзакции.
    """

    code = "payment_link_missing"
    status_code = 502

    def __init__(self, transaction_id: object) -> None:
        super().__init__(
            message=f"Отсутствует ссылка на оплату картой для транзакции {transaction_id}",
            details={"transaction_id": str(transaction_id)},
        )
