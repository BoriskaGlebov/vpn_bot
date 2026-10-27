from typing import Any

from starlette import status

from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


class AppError(Exception):
    """Базовая ошибка приложения."""

    code: str = "app_error"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Сериализует ошибку в словарь."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }

    def to_envelope(
        self,
    ) -> ErrorEnvelope:
        """Сериализует ошибку в ErrorEnvelope."""
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details or {},
            )
        )

    def __str__(self) -> str:
        """Возвращает текст ошибки с причиной, если она есть."""
        base = self.message

        if self.cause:
            return f"{base} (cause: {self.cause})"

        return base


class ReferralError(AppError):
    """Базовое исключение реферальной системы."""

    pass


class ReferralNotFoundError(ReferralError):
    """Ошибка отсутствия реферальной записи."""

    code = "referral_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, invited_user_id: int, username: str) -> None:
        super().__init__(
            message=f"Реферальная запись для пользователя @{username} не найдена",
            details={
                "invited_user_id": invited_user_id,
                "username": username,
            },
        )


class UserNotFoundError(AppError):
    """Ошибка отсутствия пользователя."""

    code = "user_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, tg_id: int) -> None:
        super().__init__(
            message=f"Пользователь с Telegram ID {tg_id} не найден.",
            details={
                "tg_id": tg_id,
            },
        )


class RoleNotFoundError(AppError):
    """Ошибка отсутствия роли."""

    code = "role_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, role_name: str) -> None:
        super().__init__(
            message=f"Роль пользователя  {role_name} не найдена.",
            details={"role_name": role_name},
        )


class SubscriptionNotFoundError(AppError):
    """Ошибка отсутствия подписки."""

    code = "subscription_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"У пользователя @{username} нет подписки / не активна.",
            details={"user_id": user_id, "username": username},
        )


class ActiveSubscriptionExistsError(AppError):
    """Ошибка наличия активной подписки."""

    code = "subscription_error"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"У пользователя @{username} уже есть активная подписка",
            details={"user_id": user_id, "username": username},
        )


class TrialAlreadyUsedError(AppError):
    """Ошибка повторного использования пробного периода."""

    code = "trial_alredy_used_error"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"Пробный период уже был использован пользователем @{username}",
            details={"user_id": user_id, "username": username},
        )


class VPNLimitError(AppError):
    """Ошибка превышения лимита VPN-конфигов."""

    code = "vpn_limit_reached"
    status_code = status.HTTP_409_CONFLICT

    def __init__(
        self,
        user_id: int,
        limit: int,
        current: int,
        username: str,
    ) -> None:
        super().__init__(
            message=f"Пользователь @{username} достиг лимита ({current}/{limit}) конфигов.",
            details={
                "user_id": user_id,
                "limit": limit,
                "current": current,
                "username": username,
            },
        )


class PaymentError(AppError):
    """Базовое исключение платежной системы."""

    code = "payment_error"
    status_code = status.HTTP_400_BAD_REQUEST
    pass


class PaymentTransactionNotFoundError(PaymentError):
    """Ошибка отсутствия транзакции."""

    code = "transaction_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(
        self, transaction_id: str | None, gateway_transaction_id: str | None = None
    ) -> None:
        super().__init__(
            message=f"Транзакция transaction_id({transaction_id or 'undefined_transaction'}) \n "
            f"gateway_id({gateway_transaction_id or 'undefined_transaction'}) \n"
            f"не найдена.",
            details={
                "transaction_id": transaction_id,
                "gateway_transaction_id": gateway_transaction_id,
            },
        )


class PaymentAlreadyProcessedError(PaymentError):
    """Ошибка повторной обработки транзакции."""

    code = "payment_already_processed"
    status_code = status.HTTP_409_CONFLICT

    def __init__(
        self,
        transaction_id: str,
        payment_status: str,
        source: str | None = None,
    ) -> None:
        """Инициализирует ошибку повторной обработки.

        Args:
            transaction_id: ID транзакции.
            payment_status: Текущий статус платежа.
            source: Источник, которым транзакция была переведена в текущий
                статус (`PaymentSource.MANUAL`/`GATEWAY`) — позволяет
                вызывающей стороне понять, кто именно оплату подтвердил.

        """
        super().__init__(
            message=(
                f"Транзакция {transaction_id} уже обработана "
                f"(текущий статус: {payment_status}, источник: {source})."
            ),
            details={
                "transaction_id": transaction_id,
                "status": payment_status,
                "source": source,
            },
        )


class PaymentConfirmationError(PaymentError):
    """Ошибка подтверждения платежа."""

    code = "payment_confirmation_failed"
    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Не удалось подтвердить транзакцию {transaction_id}.",
            details={
                "transaction_id": transaction_id,
            },
        )


class PaymentAlreadyConfirmedError(PaymentError):
    """Ошибка повторного подтверждения платежа."""

    code = "payment_already_confirmed"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Транзакция {transaction_id} уже подтверждена.",
            details={
                "transaction_id": transaction_id,
            },
        )


class PaymentCanceledError(PaymentError):
    """Ошибка отменённого платежа."""

    code = "payment_canceled"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Транзакция {transaction_id} отменена.",
            details={
                "transaction_id": transaction_id,
            },
        )


class PaymentFailedError(PaymentError):
    """Ошибка неуспешного платежа."""

    code = "payment_failed"
    status_code = status.HTTP_402_PAYMENT_REQUIRED

    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Оплата транзакции {transaction_id} завершилась ошибкой.",
            details={
                "transaction_id": transaction_id,
            },
        )


class PaymentInvalidSourceError(PaymentError):
    """Невалидное сочетание source/admin_id при подтверждении платежа.

    Поднимается `confirm_payment_flow`, когда `payment_source`
    не входит в поддерживаемый набор, либо `payment_source=MANUAL`, но
    `admin_id` не передан. Это нарушение контракта вызова, а не сбой
    инфраструктуры — раньше здесь поднимался `ValueError`, который не
    обрабатывается ни `app_error_handler`, ни `api_error_handler` и
    доходит до `unhandled_exception_handler` как 500 `internal_error`:
    по такому ответу нельзя отличить «неверный вызов» от «упала база».
    """

    code = "payment_invalid_source"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, payment_source: object, admin_id: int | None) -> None:
        super().__init__(
            message=(
                f"Неверный payment_source ({payment_source}) или не передан "
                f"admin_id для MANUAL (admin_id={admin_id})."
            ),
            details={
                "payment_source": str(payment_source),
                "admin_id": admin_id,
            },
        )


class BotChannelUnavailableError(AppError):
    """Бот недоступен по внутреннему каналу api → bot.

    Поднимается при таймауте/обрыве соединения, ответе не-2xx (в т.ч.
    401/403 при неверном или не заданном `BOT_INTERNAL_API_KEY`) и
    нераспознаваемом теле ответа. Состояние нод при этом неизвестно, поэтому
    вызывающий код не должен удалять записи в БД.
    """

    code = "bot_channel_unavailable"
    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(self, reason: str, *, cause: Exception | None = None) -> None:
        super().__init__(
            message=f"Бот недоступен по внутреннему каналу: {reason}",
            details={"reason": reason},
            cause=cause,
        )


class VPNRevokeFailedError(AppError):
    """Бот сообщил, что нода/панель не смогла отозвать доступ конфига.

    Запись в БД намеренно не удаляется: конфиг может реально существовать
    на сервере, и удаление записи лишило бы нас информации о нём.
    """

    code = "vpn_revoke_failed"
    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(self, file_name: str, detail: str | None = None) -> None:
        super().__init__(
            message=(
                f"Не удалось отозвать доступ конфига «{file_name}» на ноде, "
                "запись в БД не удалена."
            ),
            details={"file_name": file_name, "detail": detail},
        )
