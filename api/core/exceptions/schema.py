from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Детальная информация об ошибке."""

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Обёртка ответа API для ошибок."""

    error: ErrorDetail


APIErrorResponse = ErrorEnvelope
