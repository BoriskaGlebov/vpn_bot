from pydantic import BaseModel, ConfigDict, Field


class SSubscription(BaseModel):
    """Схема подписки пользователя.

    Attributes
        user_id (int): Идентификатор пользователя, которому принадлежит подписка.

    """

    user_id: int = Field(..., description="User ID")
    model_config = ConfigDict(from_attributes=True)
