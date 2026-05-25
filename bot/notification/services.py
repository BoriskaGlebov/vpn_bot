from aiogram import Bot


class NotificationService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def notify_payment_success(self, user_id: int, amount: int):
        await self.bot.send_message(
            chat_id=user_id,
            text=f"Оплата {amount} прошла успешно"
        )

    async def notify_payment_failed(self, user_id: int):
        await self.bot.send_message(
            chat_id=user_id,
            text="Оплата не прошла"
        )