from typing import Any

from starlette import status

from api.core.exceptions.schema import ErrorEnvelope, ErrorDetail


class AppError(Exception):
    """Базовое приложение-ориентированное исключение.

    Args:
        message (str): Описание ошибки.
        cause (Exception | None): Исходное исключение.

    """

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
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }

    def to_envelope(self,) -> ErrorEnvelope:
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details or {},
            )
        )

    def __str__(self) -> str:
        base = self.message

        if self.cause:
            return f"{base} (cause: {self.cause})"

        return base


class ReferralError(AppError):
    """Базовое исключение реферальной системы.

    Используется как родительский класс для всех ошибок,
    связанных с логикой рефералов.

    Позволяет централизованно обрабатывать ошибки данного домена
    (например, через FastAPI exception handler).

    Наследует:
        AppError: Базовое приложение исключений.

    """

    pass


class ReferralNotFoundError(ReferralError):
    """Ошибка: реферальная запись не найдена.

    Возникает, если для указанного приглашённого пользователя
    отсутствует запись о реферале.

    Attributes
        invited_user_id (int): User ID приглашённого пользователя,
            для которого не найдена реферальная запись.
        username (str): Telegram username приглашённого пользователя.
            для которого не найдена реферальная запись.

    Args:
        invited_user_id (int): User ID приглашённого пользователя.
        username (str): Telegram username приглашённого пользователя.


    """

    code = "referral_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, invited_user_id: int, username: str) -> None:
        """Инициализирует исключение.

        Args:
            invited_user_id (int): User ID приглашённого пользователя.
            username (str): Telegram username приглашённого пользователя.
        """
        super().__init__(
            message=f"Реферальная запись для пользователя @{username} не найдена",
            details={
                "invited_user_id": invited_user_id,
                "username": username,
            },
        )


class ReferralBonusAlreadyGivenError(ReferralError):
    """Ошибка: бонус уже был начислен.

    Возникает, если попытка начислить бонус выполняется повторно
    для одного и того же приглашённого пользователя.

    Attributes
        invited_user_id (int): User ID приглашённого пользователя,
            для которого бонус уже был начислен.
        username (str): Telegram username приглашённого пользователя,
            для которого бонус уже был начислен.

    Args:
        invited_user_id (int): User ID приглашённого пользователя.
        username (str): Telegram username приглашённого пользователя.

    """

    code = "referral_bonus_already_given"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, invited_user_id: int, username: str) -> None:
        super().__init__(
            message=f"Бонус за пользователя @{username} уже был начислен",
            details={
                "invited_user_id": invited_user_id,
                "username": username,
            },
        )


class UserNotFoundError(AppError):
    """Пользователь не найден."""

    code = "user_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, tg_id: int) -> None:
        """Инициализирует исключение.

        Args:
            tg_id (int): Telegram ID  пользователя.

        """
        super().__init__(
            message=f"Пользователь с Telegram ID {tg_id} не найден.",
            details={
                "tg_id": tg_id,
            },
        )


class RoleNotFoundError(AppError):
    """Роль не найден."""

    code = "role_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, role_name: str) -> None:
        super().__init__(
            message=f"Роль пользователя  {role_name} не найдена.",
            details={"role_name": role_name},
        )


class SubscriptionNotFoundError(AppError):
    """У пользователя нет подписки."""

    code = "subscription_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"У пользователя @{username} нет подписки / не активна.",
            details={"user_id": user_id, "username": username},
        )


class ActiveSubscriptionExistsError(AppError):
    """У пользователя уже есть активная подписка."""

    code = "subscription_error"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"У пользователя @{username} уже есть активная подписка",
            details={"user_id": user_id, "username": username},
        )


class TrialAlreadyUsedError(AppError):
    """Пробный период уже использован."""

    code = "trial_error"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, user_id: int, username: str) -> None:
        super().__init__(
            message=f"Пробный период уже был использован пользователем @{username}",
            details={"user_id": user_id, "username": username},
        )


class VPNLimitError(AppError):
    """Пользователь достиг лимита VPN-конфигов.

    Args:
        user_id (int): ID пользователя.
        limit (int): Максимальное количество конфигов.

    """

    code = "vpn_limit_reached"
    status_code = status.HTTP_403_FORBIDDEN

    def __init__(
        self,
        user_id: int,
        limit: int,
        username: str,
    ) -> None:
        super().__init__(
            message=f"Пользователь @{username} достиг лимита ({limit}) конфигов.",
            details={
                "user_id": user_id,
                "limit": limit,
                "username": username,
            },
        )


class PaymentError(AppError):
    """Базовое исключение платежной системы."""

    code = "payment_error"
    status_code = status.HTTP_400_BAD_REQUEST
    pass


class PaymentTransactionNotFoundError(PaymentError):
    """Транзакция не найдена."""

    code = "transaction_not_found"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(
        self, transaction_id: str | None, gateway_transaction_id: str | None = None
    ) -> None:
        super().__init__(
            message=f"Транзакция transaction_id({transaction_id or 'undefined_transaction'})\n"
            f"gateway_id({gateway_transaction_id or 'undefined_transaction'}) \n"
            f"не найдена.",
            details={
                "transaction_id": transaction_id,
                "gateway_transaction_id": gateway_transaction_id,
            },
        )


class PaymentAlreadyProcessedError(PaymentError):
    """Транзакция уже обработана."""

    code = "payment_already_processed"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, transaction_id: str, status: str) -> None:
        super().__init__(
            message=(
                f"Транзакция {transaction_id} уже обработана "
                f"(текущий статус: {status})."
            ),
            details={
                "transaction_id": transaction_id,
                "status": status,
            },
        )
        self.transaction_id = transaction_id
        self.status = status


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
    """Платеж уже подтвержден."""

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
    """Транзакция отменена."""

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
    """Ошибка оплаты."""

    code = "payment_failed"
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    
    def __init__(self, transaction_id: str) -> None:
        super().__init__(
            message=f"Оплата транзакции {transaction_id} завершилась ошибкой.",
            details={
                "transaction_id": transaction_id,
            },
        )


class InvalidPaymentStatusTransitionError(PaymentError):
    """Недопустимый переход статуса платежа."""

    code = "invalid_payment_status_transition"
    status_code = status.HTTP_409_CONFLICT
    
    def __init__(
        self,
        transaction_id: str,
        from_status: str,
        to_status: str,
    ) -> None:
        super().__init__(
            message=(
                f"Недопустимый переход статуса транзакции "
                f"{transaction_id}: {from_status} -> {to_status}."
            ),
            details={
                "transaction_id": transaction_id,
                "from_status": from_status,
                "to_status": to_status,
            },
        )
