from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Детальная информация об ошибке.

    Attributes
        code: Машиночитаемый код ошибки.
        message: Человекочитаемое описание ошибки.
        details: Дополнительные структурированные данные об ошибке.

    """

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Обёртка ответа API для ошибок.

    Attributes
        error: Структура с описанием ошибки.

    """

    error: ErrorDetail


#: Алиас типа ответа API с ошибкой.
APIErrorResponse = ErrorEnvelope
