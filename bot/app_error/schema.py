from typing import Any

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """Информация об ошибке API.

    Attributes
        code: Машиночитаемый код ошибки.
        message: Человекочитаемое описание ошибки.
        details: Дополнительные данные об ошибке в виде словаря.
            Может содержать информацию о причине ошибки,
            параметрах запроса или других диагностических данных.

    """

    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    """Стандартная оболочка ответа API при возникновении ошибки.

    Используется для унификации структуры всех ошибочных ответов
    REST API.

    Attributes
        error: Объект с подробной информацией об ошибке.

    """

    error: ErrorDetail
