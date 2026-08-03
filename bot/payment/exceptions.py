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
