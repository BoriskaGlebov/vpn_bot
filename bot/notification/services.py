from aiogram import Bot


class NotificationService:
    """Отправляет пользователю уведомления о результате оплаты."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def notify_payment_success(self, user_id: int, amount: int) -> None:
        """Уведомляет пользователя об успешной оплате.

        Args:
            user_id: Telegram ID пользователя.
            amount: Сумма оплаты.

        """
        await self.bot.send_message(
            chat_id=user_id, text=f"Оплата {amount} прошла успешно"
        )

    async def notify_payment_failed(self, user_id: int) -> None:
        """Уведомляет пользователя о неудачной оплате.

        Args:
            user_id: Telegram ID пользователя.

        """
        await self.bot.send_message(chat_id=user_id, text="Оплата не прошла")
