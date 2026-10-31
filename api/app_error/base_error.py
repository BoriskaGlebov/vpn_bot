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


class PromoCodeError(AppError):
    """Базовое исключение промокодов."""

    code = "promo_error"
    status_code = status.HTTP_400_BAD_REQUEST


class PromoCodeNotFoundError(PromoCodeError):
    """Ошибка отсутствия промокода с указанным кодом."""

    code = "promo_code_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, code: str) -> None:
        super().__init__(
            message=f"Промокод «{code}» не найден.",
            details={"code": code},
        )


class PromoCodeInactiveError(PromoCodeError):
    """Промокод деактивирован администратором либо вне срока действия."""

    code = "promo_code_inactive"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(
            message=f"Промокод «{code}» сейчас недействителен ({reason}).",
            details={"code": code, "reason": reason},
        )


class PromoCodeLimitReachedError(PromoCodeError):
    """Промокод исчерпал лимит применений."""

    code = "promo_code_limit_reached"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str, max_uses: int) -> None:
        super().__init__(
            message=f"Промокод «{code}» уже использован максимальное число раз ({max_uses}).",
            details={"code": code, "max_uses": max_uses},
        )


class PromoCodeAlreadyUsedError(PromoCodeError):
    """Пользователь уже применял этот промокод ранее."""

    code = "promo_code_already_used"
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, code: str, user_id: int) -> None:
        super().__init__(
            message=f"Вы уже использовали промокод «{code}» ранее.",
            details={"code": code, "user_id": user_id},
        )


class InvalidNodeNameError(AppError):
    """Указанное имя ноды отсутствует в конфигурации vpn.nodes."""

    code = "invalid_node_name"
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT

    def __init__(self, node_name: str, known: frozenset[str]) -> None:
        super().__init__(
            message=f"Нода «{node_name}» не найдена в конфигурации.",
            details={"node_name": node_name, "known_nodes": sorted(known)},
        )


class ExpenseNotFoundError(AppError):
    """Ошибка отсутствия записи о расходе."""

    code = "expense_not_found"
    status_code = status.HTTP_404_NOT_FOUND

    def __init__(self, expense_id: int) -> None:
        super().__init__(
            message=f"Расход с ID {expense_id} не найден.",
            details={"expense_id": expense_id},
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


class UserVPNRevokeIncompleteError(AppError):
    """Не все VPN-конфиги пользователя удалось отозвать при удалении (#290).

    Поднимается `UserAdmin.on_model_delete`, когда хотя бы один из конфигов
    пользователя не подтвердил отзыв доступа (бот недоступен или нода
    ответила ошибкой). Удаление пользователя прерывается целиком: частично
    удалённый пользователь — ещё один источник расхождения между БД и
    нодами, а не решение твоей проблемы. Конфиги, для которых отзыв уже прошёл
    успешно, доступа на ноде больше не имеют — повторная попытка удаления
    безопасна (бот вернёт `NOT_FOUND` для них снова).
    """

    code = "user_vpn_revoke_incomplete"
    status_code = status.HTTP_502_BAD_GATEWAY

    def __init__(
        self, user_id: int, username: str | None, failed_configs: list[str]
    ) -> None:
        super().__init__(
            message=(
                f"Не удалось отозвать доступ всех VPN-конфигов пользователя "
                f"@{username or user_id} на нодах, удаление прервано. "
                f"Остались неотозванными: {', '.join(failed_configs)}."
            ),
            details={
                "user_id": user_id,
                "username": username,
                "failed_configs": failed_configs,
            },
        )
