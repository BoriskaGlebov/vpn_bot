from uuid import UUID

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from loguru import logger

from bot.app_error.base_error import SubscriptionActivationFailedError
from bot.core.config import settings_bot
from bot.payment.schemas import SConfirmPaymentResponse
from bot.redis_service import RedisPaymentMessageStorage
from bot.utils.formatting import format_subscription_end_date
from bot.utils.start_stop_bot import send_to_admins

m_subscription = settings_bot.messages.modes.subscription


class NotificationService:
    """Уведомляет пользователя и администраторов о результате оплаты подписки.

    Оплата подтверждается по вебхуку платёжного шлюза (см. `PaymentWebhookService`).
    """

    def __init__(
        self, bot: Bot, payment_mess_storage: RedisPaymentMessageStorage
    ) -> None:
        self.bot = bot
        self.payment_mess_storage = payment_mess_storage

    async def _deliver_outcome_message(
        self, transaction_id: UUID, tg_id: int, text: str
    ) -> None:
        """Показывает пользователю итог оплаты по транзакции.

        Если для транзакции сохранено сообщение с кнопкой "Перейти к оплате"
        (см. `RedisPaymentMessageStorage`), редактирует именно его — убирает
        устаревшую ссылку и кнопку, заменяет текст на итоговый статус. Так
        пользователь не может повторно открыть ссылку на уже решённую
        оплату. Если сообщение не найдено (например, оплата шла переводом,
        а не картой, либо запись истекла), отправляет обычное новое
        сообщение.

        Args:
            transaction_id: UUID транзакции — ключ, по которому было
                сохранено расположение сообщения с оплатой.
            tg_id: Telegram ID пользователя — куда отправить новое
                сообщение, если редактирование недоступно.
            text: Итоговый текст (успех или неудача оплаты).

        Raises
            TelegramBadRequest: Если ни отредактировать исходное сообщение,
                ни отправить новое не удалось (например, пользователь
                заблокировал бота).

        """
        location = await self.payment_mess_storage.pop(transaction_id)
        if location is not None:
            try:
                await self.bot.edit_message_text(
                    chat_id=location["chat_id"],
                    message_id=location["message_id"],
                    text=text,
                    reply_markup=None,
                )
                return
            except TelegramBadRequest:
                logger.warning(
                    "Не удалось отредактировать сообщение с оплатой "
                    "transaction_id={} — отправляю новое",
                    transaction_id,
                )
        await self.bot.send_message(chat_id=tg_id, text=text)

    async def notify_payment_confirmed(self, confirm: SConfirmPaymentResponse) -> None:
        """Уведомляет об оплате, автоматически подтверждённой платёжным шлюзом.

        Переиспользует те же тексты, что и ручное подтверждение оплаты
        администратором (`m_subscription.accept_paid`), чтобы пользователь и
        админы видели единый стиль независимо от способа оплаты.

        Args:
            confirm: Результат подтверждения оплаты — транзакция, обновлённые
                данные подписки пользователя и результат начисления
                реферального бонуса.

        Raises
            SubscriptionActivationFailedError: Если после подтверждения оплаты
                у пользователя не оказалось активной подписки с указанным
                типом — сигнал рассинхронизации, требующий ручной проверки.

        """
        tx = confirm.transaction_res
        user = confirm.subscription_res
        if user.current_subscription is None or user.current_subscription.type is None:
            raise SubscriptionActivationFailedError(
                tg_id=tx.tg_id, reason="подписка не найдена после оплаты по вебхуку"
            )
        sub_type = user.current_subscription.type.upper()
        end_date = format_subscription_end_date(user.current_subscription.end_date)

        try:
            await self._deliver_outcome_message(
                transaction_id=tx.id,
                tg_id=tx.tg_id,
                text=m_subscription.accept_paid.user.format(
                    sub_type=sub_type,
                    months=tx.subscription_months,
                    amount=tx.amount,
                    end_date=end_date,
                ),
            )
            referral = confirm.referral_res
            if referral.success and referral.inviter_telegram_id:
                await self.bot.send_message(
                    chat_id=referral.inviter_telegram_id,
                    text=m_subscription.accept_paid.bonus.format(
                        user_info=f"@{user.username}"
                    ),
                )
        except TelegramBadRequest:
            logger.warning(
                "Не удалось уведомить пользователя об оплате картой: tg_id={}",
                tx.tg_id,
            )
            await send_to_admins(
                bot=self.bot,
                message_text=m_subscription.accept_paid.error.format(user_id=tx.tg_id),
            )

        await send_to_admins(
            bot=self.bot,
            message_text=m_subscription.accept_paid.admin.format(
                user_id=tx.tg_id,
                sub_type=sub_type,
                username=user.username,
                info=m_subscription.gateway_alert.confirmed_info,
            ),
        )

    async def notify_payment_failed(
        self, transaction_id: UUID, tg_id: int, is_chargeback: bool = False
    ) -> None:
        """Уведомляет о платеже, не подтверждённом платёжным шлюзом.

        Args:
            transaction_id: UUID транзакции — для поиска сообщения с оплатой,
                которое нужно отредактировать (см. `_deliver_outcome_message`).
            tg_id: Telegram ID пользователя.
            is_chargeback: True, если провайдер вернул статус CHARGEBACKED
                (уже полученные деньги возвращены плательщику) — в отличие от
                обычной отмены (пользователь не завершил оплату), это требует
                внимания администратора.

        """
        try:
            await self._deliver_outcome_message(
                transaction_id=transaction_id,
                tg_id=tg_id,
                text=m_subscription.decline_paid.user,
            )
        except TelegramBadRequest:
            logger.warning(
                "Не удалось уведомить пользователя о неудачной оплате: tg_id={}",
                tg_id,
            )

        if is_chargeback:
            admin_text = m_subscription.gateway_alert.chargeback + (
                m_subscription.decline_paid.admin.format(user_id=tg_id)
            )
            await send_to_admins(bot=self.bot, message_text=admin_text)
        else:
            logger.info(
                "Оплата картой отменена/не завершена пользователем: tg_id={}", tg_id
            )
