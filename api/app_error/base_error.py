from typing import Any

from starlette import status

from api.core.exceptions.schema import ErrorDetail, ErrorEnvelope


class AppError(Exception):
    """Базовое приложение-ориентированное исключение.

    Используется как корневой класс всех доменных ошибок приложения.
    Позволяет унифицировать формат ошибок и их сериализацию в API.

    Attributes
        code: Машиночитаемый код ошибки.
        status_code: HTTP статус ответа.
        message: Текстовое описание ошибки.
        details: Дополнительные структурированные данные.
        cause: Первопричина ошибки (исходное исключение).

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
        """Инициализирует базовую ошибку приложения.

        Args:
            message: Описание ошибки.
            details: Дополнительные данные об ошибке.
            cause: Исходное исключение, вызвавшее ошибку.

        """
        super().__init__(message)

        self.message = message
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Преобразует исключение в словарь API формата.

        Returns
            Словарь с описанием ошибки.

        """
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
        """Преобразует ошибку в Pydantic-обёртку.

        Returns
            ErrorEnvelope с данными ошибки.

        """
        return ErrorEnvelope(
            error=ErrorDetail(
                code=self.code,
                message=self.message,
                details=self.details or {},
            )
        )

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки.

        Returns
            Текст ошибки с указанием причины, если она есть.

        """
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
    """Ошибка отсутствия реферальной записи.

    Attributes
        invited_user_id: ID приглашённого пользователя.
        username: Telegram username приглашённого пользователя.

    """

    code = "referral_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, invited_user_id: int, username: str) -> None:
        """Инициализирует ошибку отсутствия реферала.

        Args:
            invited_user_id: ID приглашённого пользователя.
            username: Telegram username приглашённого пользователя.

        """
        super().__init__(
            message=f"Реферальная запись для пользователя @{username} не найдена",
            details={
                "invited_user_id": invited_user_id,
                "username": username,
            },
        )


class ReferralBonusAlreadyGivenError(ReferralError):
    """Ошибка повторного начисления реферального бонуса."""

    code = "referral_bonus_already_given"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, invited_user_id: int, username: str) -> None:
        """Инициализирует ошибку повторного бонуса.

        Args:
            invited_user_id: ID пользователя.
            username: Telegram username.

        """
        super().__init__(
            message=f"Бонус за пользователя @{username} уже был начислен",
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
        """Инициализирует ошибку отсутствия пользователя.

        Args:
            tg_id: Telegram ID пользователя.

        """
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
        """Инициализирует ошибку отсутствия роли.

        Args:
            role_name: Название роли.

        """
        super().__init__(
            message=f"Роль пользователя  {role_name} не найдена.",
            details={"role_name": role_name},
        )


class SubscriptionNotFoundError(AppError):
    """Ошибка отсутствия подписки."""

    code = "subscription_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, user_id: int, username: str) -> None:
        """Инициализирует ошибку отсутствия подписки.

        Args:
            user_id: ID пользователя.
            username: Telegram username.

        """
        super().__init__(
            message=f"У пользователя @{username} нет подписки / не активна.",
            details={"user_id": user_id, "username": username},
        )


class ActiveSubscriptionExistsError(AppError):
    """Ошибка наличия активной подписки."""

    code = "subscription_error"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, user_id: int, username: str) -> None:
        """Инициализирует ошибку активной подписки.

        Args:
            user_id: ID пользователя.
            username: Telegram username.

        """
        super().__init__(
            message=f"У пользователя @{username} уже есть активная подписка",
            details={"user_id": user_id, "username": username},
        )


class TrialAlreadyUsedError(AppError):
    """Ошибка повторного использования пробного периода."""

    code = "trial_alredy_used_error"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, user_id: int, username: str) -> None:
        """Инициализирует ошибку пробного периода.

        Args:
            user_id: ID пользователя.
            username: Telegram username.

        """
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
        username: str,
    ) -> None:
        """Инициализирует ошибку лимита VPN.

        Args:
            user_id: ID пользователя.
            limit: Максимально допустимое количество конфигов.
            username: Telegram username.

        """
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
    """Ошибка отсутствия транзакции."""

    code = "transaction_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(
        self, transaction_id: str | None, gateway_transaction_id: str | None = None
    ) -> None:
        """Инициализирует ошибку отсутствия транзакции.

        Args:
            transaction_id: ID транзакции.
            gateway_transaction_id: ID транзакции в платёжном шлюзе.

        """
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

    def __init__(self, transaction_id: str, payment_status: str) -> None:
        """Инициализирует ошибку повторной обработки.

        Args:
            transaction_id: ID транзакции.
            payment_status: Текущий статус платежа.

        """
        super().__init__(
            message=(
                f"Транзакция {transaction_id} уже обработана "
                f"(текущий статус: {payment_status})."
            ),
            details={
                "transaction_id": transaction_id,
                "status": payment_status,
            },
        )


class PaymentConfirmationError(PaymentError):
    """Ошибка подтверждения платежа."""

    code = "payment_confirmation_failed"
    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(self, transaction_id: str) -> None:
        """Инициализирует ошибку подтверждения.

        Args:
            transaction_id: ID транзакции.

        """
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
        """Инициализирует ошибку повторного подтверждения.

        Args:
            transaction_id: ID транзакции.

        """
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
        """Инициализирует ошибку отменённого платежа.

        Args:
            transaction_id: ID транзакции.

        """
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
        """Инициализирует ошибку неуспешного платежа.

        Args:
            transaction_id: ID транзакции.

        """
        super().__init__(
            message=f"Оплата транзакции {transaction_id} завершилась ошибкой.",
            details={
                "transaction_id": transaction_id,
            },
        )


class InvalidPaymentStatusTransitionError(PaymentError):
    """Ошибка недопустимого перехода статуса платежа."""

    code = "invalid_payment_status_transition"
    status_code = status.HTTP_409_CONFLICT

    def __init__(
        self,
        transaction_id: str,
        from_status: str,
        to_status: str,
    ) -> None:
        """Инициализирует ошибку перехода статуса.

        Args:
            transaction_id: ID транзакции.
            from_status: Исходный статус.
            to_status: Новый статус.

        """
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
