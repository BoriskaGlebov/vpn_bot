from loguru import logger

from bot.referrals.adapter import ReferralAPIAdapter
from bot.referrals.schemas import (
    GrantReferralBonusRequest,
    RegisterReferralRequest,
)
from bot.users.schemas import SUserOut


class ReferralService:
    """Сервис для взаимодействия с реферальной системой.

    Отвечает за:
        - регистрацию реферальных связей
        - начисление бонусов пригласителям через внешний API
    """

    def __init__(
        self,
        adapter: ReferralAPIAdapter,
    ) -> None:
        """Инициализирует сервис рефералов.

        Args:
            adapter: Адаптер для взаимодействия с API реферальной системы.

        """
        self.api_adapter = adapter

    async def register_referral(
        self,
        invited_user: SUserOut,
        inviter_telegram_id: int | None,
    ) -> None:
        """Регистрирует реферальную связь для нового пользователя.

        Регистрация выполняется только если:
            - указан inviter_telegram_id
            - пользователь не использовал триальный период

        Args:
            invited_user: Данные приглашённого пользователя.
            inviter_telegram_id: Telegram ID пригласителя.
                Если None, регистрация пропускается.

        Returns
            None

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
        """Начисляет бонус пригласителю за приглашённого пользователя.

        Логика полностью делегирована внешнему API.

        Args:
            invited_user: Данные приглашённого пользователя.
            months: Количество месяцев бонуса (по умолчанию 1).

        Returns
            tuple:
                - bool: True, если бонус успешно начислен, иначе False
                - int | None: Telegram ID пригласителя, если бонус начислен,
                  иначе None

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
