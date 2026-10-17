from bot.app_error.base_error import AppError


class PaymentProviderError(AppError):
    """Ошибка при обращении к внешнему платёжному провайдеру (например, Platega).

    Наследуется от `AppError`, чтобы попадать в общий `ErrorHandlerMiddleware`
    (который распознаёт только `AppError`/`APIClientError`) и корректно
    превращаться в `ErrorEnvelope`, а не в generic "unexpected_error" —
    до этого класса ошибки провайдера пробрасывались как голый
    `httpx.HTTPError`, не наследующий `AppError`.

    Args:
        message (str): Описание ошибки.
        cause (Optional[Exception]): Исходное исключение (обычно `httpx.HTTPError`).

    """

    code: str = "payment_provider_error"
    status_code: int = 502


class PaymentAmountMismatchError(AppError):
    """Сумма в вебхуке платёжного провайдера не совпадает с суммой транзакции.

    Поднимается перед подтверждением оплаты по вебхуку (см. #257) — решение
    "платёж прошёл" не должно приниматься по одной строке статуса, без
    проверки содержимого. Транзакция в этом случае не подтверждается,
    остаётся в PENDING до ручной проверки администратором.

    Args:
        transaction_id: Идентификатор транзакции.
        expected_amount (Decimal): Сумма транзакции, ожидаемая по данным БД.
        received_amount (Decimal | None): Сумма, присланная в вебхуке
            (``None``, если провайдер её не прислал).

    """

    code: str = "payment_amount_mismatch"
    status_code: int = 409

    def __init__(
        self,
        transaction_id: object,
        expected_amount: object,
        received_amount: object,
    ) -> None:
        super().__init__(
            message=(
                f"Сумма вебхука ({received_amount}) не совпадает с суммой "
                f"транзакции {transaction_id} ({expected_amount})"
            ),
            details={
                "transaction_id": str(transaction_id),
                "expected_amount": str(expected_amount),
                "received_amount": str(received_amount),
            },
        )


class PaymentUnknownStatusError(AppError):
    """Платёжный провайдер прислал статус, не входящий в известный набор.

    Поднимается, когда `parse_webhook` не смог сопоставить статус провайдера
    ни одному из известных терминальных состояний (см. #259) — событие
    трактуется как PENDING, но в отличие от штатного "платёж пока не
    завершён" требует внимания администратора: если это новый терминальный
    статус провайдера, транзакция иначе навсегда останется в PENDING без
    единого уведомления.

    Args:
        transaction_id: Идентификатор транзакции.
        provider_status: Статус, присланный провайдером (как есть, без
            нормализации).

    """

    code: str = "payment_unknown_status"
    status_code: int = 409

    def __init__(
        self,
        transaction_id: object,
        provider_status: object,
    ) -> None:
        super().__init__(
            message=(
                f"Платёжный провайдер прислал неизвестный статус "
                f"'{provider_status}' для транзакции {transaction_id}"
            ),
            details={
                "transaction_id": str(transaction_id),
                "provider_status": str(provider_status),
            },
        )
