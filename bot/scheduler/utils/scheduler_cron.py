import asyncio
from dataclasses import asdict
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.core.config import logger, settings_bot
from bot.expense.keyboards.inline_kb import expense_reminder_kb
from bot.scheduler.services import SchedulerBotService
from bot.utils.start_stop_bot import send_to_admins

MONTH_NAMES = [
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]

m_expense = settings_bot.messages.modes.expense

scheduler = AsyncIOScheduler()


async def scheduled_check(
    service: SchedulerBotService,
) -> None:
    """Запускает плановую проверку подписок пользователей.

    Функция вызывается по расписанию и инициирует проверку всех подписок,
    обновляя их статусы в зависимости от срока действия. APScheduler не
    прокидывает исключения джобы никуда, кроме собственного логгера, поэтому
    здесь важно перехватить и залогировать/сообщить о любой ошибке самим —
    иначе сбой плановой проверки останется незамеченным.

    Args:
        service: Сервис планировщика, инкапсулирующий проверку подписок
            и рассылку уведомлений/удаление конфигов.

    """
    start_time = datetime.now()
    logger.info("⏰ Запуск плановой проверки подписок...")

    try:
        stats = await service.check_all_subscriptions()  # type: ignore
        elapsed = (datetime.now() - start_time).total_seconds()

        logger.success(
            "✅ Проверка подписок завершена. Пользователей: {checked}, истекло: {expired}, "
            "уведомлено: {notified}, конфигов удалено: {configs_deleted}. "
            "⏱ Время выполнения: {elapsed:.2f} сек.",
            **asdict(stats),
            elapsed=elapsed,
        )
        await asyncio.sleep(0.05)

    except TelegramForbiddenError as e:
        logger.exception(f"❌ Ошибка при проверке подписок: {e}")

    except Exception as e:
        logger.exception("❌ Непредвиденная ошибка плановой проверки подписок: {}", e)
        await send_to_admins(
            bot=service.bot,
            message_text=(
                "⚠️ Плановая проверка подписок упала с необработанной ошибкой.\n\n"
                f"📌 {type(e).__name__}: {e}"
            ),
        )


async def expense_reminder(bot_instance: Bot) -> None:
    """Ежемесячное напоминание администраторам о внесении расходов.

    Вызывается по cron 1-го числа каждого месяца. Напоминает внести
    расходы за ПРЕДЫДУЩИЙ месяц.

    Args:
        bot_instance: Экземпляр бота Telegram.

    """
    try:
        now = datetime.now(tz=settings_bot.core.tzinfo)
        prev_month = now.month - 1 if now.month > 1 else 12
        prev_year = now.year if now.month > 1 else now.year - 1
        month_name = MONTH_NAMES[prev_month - 1]
        text = m_expense.reminder.format(month_name=month_name, year=prev_year)
        await send_to_admins(
            bot=bot_instance,
            message_text=text,
            reply_markup=expense_reminder_kb(),
        )
        logger.info(
            "📅 Напоминание о расходах за {} {} отправлено", month_name, prev_year
        )
    except Exception as e:
        logger.exception("❌ Ошибка при отправке напоминания о расходах: {}", e)
