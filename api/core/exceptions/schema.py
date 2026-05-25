from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}

class ErrorEnvelope(BaseModel):
    error: ErrorDetail

APIErrorResponse = ErrorEnvelope