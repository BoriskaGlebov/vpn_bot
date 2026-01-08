from pydantic import BaseModel, ConfigDict


class SReferralByInvite(BaseModel):
    """Схема для поиска реферала по ID приглашенного пользователя.

    Используется для передачи фильтров в DAO при поиске записи
    о реферале в базе данных.

    Attributes
        invited_id (int): ID приглашенного пользователя.

    """

    invited_id: int
    model_config = ConfigDict(from_attributes=True)
