from loguru import logger

from bot.referrals.adapter import ReferralAPIAdapter
from shared.schemas.referral import (
    GrantReferralBonusRequest,
    RegisterReferralRequest,
)
from shared.schemas.users import SUserOut

# TODO Докумнетацию надо переделать


class ReferralService:
    """Сервис для работы с реферальной системой.

    Отвечает за регистрацию приглашений и начисление бонусов за приглашенных пользователей.
    """

    def __init__(
        self,
        adapter: ReferralAPIAdapter,
    ) -> None:
        self.api_adapter = adapter

    async def register_referral(
        self,
        invited_user: SUserOut,
        inviter_telegram_id: int | None,
    ) -> None:
        """Регистрирует приглашение нового пользователя.

        Args:
            invited_user (SUserOut): Данные приглашенного пользователя.
            inviter_telegram_id (Optional[int]): Telegram ID пригласителя.
                Если None, регистрация не производится.

        Returns
            None: Метод не возвращает значения.

        """
        if not inviter_telegram_id or invited_user.has_used_trial:
            return
        payload = RegisterReferralRequest(
            invited_user_id=invited_user.telegram_id,
            inviter_telegram_id=inviter_telegram_id,
        )

        await self.api_adapter.register_referral(payload)

        logger.info(
            "Реферал зарегистрирован через API: invited={}, inviter={}",
            invited_user.telegram_id,
            inviter_telegram_id,
        )

    async def grant_referral_bonus(
        self, invited_user: SUserOut, months: int = 1
    ) -> tuple[bool, int | None]:
        """Начисляет бонус пригласителю за регистрацию нового пользователя.

        Метод выполняет следующие шаги:
            1. Проверяет наличие реферальной записи для приглашенного пользователя.
            2. Проверяет, был ли уже начислен бонус.
            3. Если пригласитель не имеет активной подписки, создаёт стандартную.
               Иначе продлевает текущую подписку на указанное количество месяцев.
            4. Отмечает факт начисления бонуса и сохраняет дату.

        Args:
            invited_user (SUserOut): Объект данных пользователя, который был приглашен.
            months (int, optional): Количество месяцев подписки, которое будет начислено.
                По умолчанию 1.

        Returns
            Tuple[bool, Optional[int]]:
                - bool: True, если бонус успешно начислен, False — если бонус уже начислен
                  или приглашение не найдено.
                - Optional[int]: Telegram ID пригласителя, если бонус был начислен, иначе None.

        """
        payload = GrantReferralBonusRequest(
            invited_user_id=invited_user.telegram_id,
            months=months,
        )

        response = await self.api_adapter.grant_bonus(payload)

        if not response.success:
            logger.info(
                "Бонус не выдан (API): invited={}",
                invited_user.telegram_id,
            )
            return False, None

        logger.info(
            "Бонус выдан через API: inviter={}, invited={}, months={}",
            response.inviter_telegram_id,
            invited_user.telegram_id,
            months,
        )

        return True, response.inviter_telegram_id
