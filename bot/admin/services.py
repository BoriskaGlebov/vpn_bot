from sqlalchemy.ext.asyncio import AsyncSession

from bot.users.schemas import SUserOut


class AdminService:
    """Сервис для бизнес-логики управления пользователями и их ролями."""

    @staticmethod
    async def get_user_by_telegram_id(
        session: AsyncSession, telegram_id: int
    ) -> SUserOut:
        pass

    @staticmethod
    async def get_users_by_filter(
        session: AsyncSession, filter_type: str
    ) -> list[SUserOut]:
        pass

    # TODO В константы или enum такое выносят
    @staticmethod
    async def format_user_text(suser: SUserOut, key: str = "user") -> str:
        pass

    @staticmethod
    async def change_user_role(
        session: AsyncSession, telegram_id: int, role_name: str
    ) -> SUserOut:
        pass

    @staticmethod
    async def extend_user_subscription(
        session: AsyncSession, telegram_id: int, months: int
    ) -> SUserOut:
        pass
