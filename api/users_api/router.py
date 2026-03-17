# from typing import List
#
# from fastapi import APIRouter, Depends
# from sqlalchemy.ext.asyncio import AsyncSession
#
# from api.core.dependencies import get_session
# from api.users_api.schemas import SUserBase
# from bot.users.dao import UserDAO
#
# router = APIRouter(prefix="/users", tags=["AI-agent", "users"])
#
#
# @router.get("/", response_model=List[SUserBase])
# async def list_users(session: AsyncSession = Depends(get_session)):
#     """Получить всех пользователей."""
#     result = await UserDAO.find_all(session=session)
#     print(type(result))
#     return [SUserBase.model_validate(u) for u in result]
