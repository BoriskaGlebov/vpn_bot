# from datetime import datetime
# from typing import Optional, List
#
# from pydantic import BaseModel, ConfigDict
#
# from bot.subscription.models import SubscriptionType
#
#
# class SubscriptionRead(BaseModel):
#     """Схема подписки пользователя."""
#     id: int
#     type: Optional[SubscriptionType] = None
#     is_active: bool
#     start_date: datetime
#     end_date: Optional[datetime] = None
#
#     model_config = ConfigDict(from_attributes=True)
#
# class SRoleRead(BaseModel):
#     """Схема роли пользователя (для вложенной выдачи)."""
#     id: int
#     name: str
#     description: Optional[str] = None
#
#     model_config = ConfigDict(from_attributes=True)
#
# class SUserBase(BaseModel):
#     """Базовая схема пользователя без связанных данных."""
#     id: int
#     telegram_id: int
#     username: str
#     first_name: Optional[str] = None
#     last_name: Optional[str] = None
#     has_used_trial: bool
#     vpn_files_count: int
#
#     model_config = ConfigDict(from_attributes=True)
#
# class SUserRead(SUserBase):
#     """Расширенная схема пользователя с ролями и подписками."""
#     role: Optional[SRoleRead] = None
#     current_subscription: Optional[SubscriptionRead] = None
#     subscriptions: Optional[List[SubscriptionRead]] = []
#
#     model_config = ConfigDict(from_attributes=True)
#
#
