from pydantic import BaseModel


class SHealthResponse(BaseModel):
    """Представляет состояние здоровья FastAPI-сервиса.

    Attributes
        status (str): Статус сервиса. Обычно "ok", если сервис работает корректно.
        message (str): Читаемое человеком сообщение о состоянии сервиса.

    """

    status: str
    message: str
