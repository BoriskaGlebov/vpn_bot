from datetime import datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    PromoCodeAlreadyUsedError,
    PromoCodeInactiveError,
    PromoCodeLimitReachedError,
    PromoCodeNotFoundError,
)
from api.core.config import settings_api
from api.promo.dao import PromoCodeDAO, PromoCodeUsageDAO
from api.promo.models import PromoCode
from api.promo.schemas import (
    SPromoCodeFilter,
    SPromoCodeUsageCreate,
    SPromoUsageFilter,
    SPromoValidationResult,
)
from shared.enums.promo_enum import PromoDiscountType

# Минимальная итоговая сумма к оплате — ноль/отрицательная сумма не
# принимается платёжным шлюзом (см. `CreatePaymentDTO.__post_init__` в bot/).
MIN_FINAL_AMOUNT = 1


class PromoService:
    """Сервис промокодов: проверка применимости и фиксация применения.

    Отвечает за всю арифметику скидки (владелец определения промокода —
    api/, см. CLAUDE.md), а не только за хранение — bot/ знает лишь
    базовую цену подписки и передаёт её сюда для расчёта.
    """

    def _calculate_discount(
        self, promo: PromoCode, base_amount: int
    ) -> tuple[int, int]:
        """Считает сумму скидки и итоговую сумму к оплате.

        Args:
            promo: Промокод.
            base_amount: Сумма до применения скидки.

        Returns
            tuple[int, int]: (discount_amount, final_amount). Скидка
            ограничивается так, чтобы итоговая сумма оставалась не меньше
            `MIN_FINAL_AMOUNT` — платёжный шлюз не принимает нулевую или
            отрицательную сумму.

        """
        if promo.discount_type == PromoDiscountType.PERCENT:
            raw_discount = base_amount * promo.discount_value // 100
        else:
            raw_discount = promo.discount_value

        discount_amount = max(0, min(raw_discount, base_amount - MIN_FINAL_AMOUNT))
        final_amount = base_amount - discount_amount
        return discount_amount, final_amount

    async def validate_code(
        self,
        session: AsyncSession,
        code: str,
        user_id: int,
        base_amount: int,
    ) -> SPromoValidationResult:
        """Проверяет, что промокод применим к данному пользователю и сумме.

        Не изменяет состояние (счётчик применений, записи об использовании) —
        только читает и считает скидку. Применение фиксируется отдельно,
        при подтверждённой оплате (см. `PaymentService.confirm_payment_flow`),
        чтобы отменённые/неоплаченные транзакции не "жгли" код впустую.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            code: Код промокода, введённый пользователем.
            user_id: ID пользователя, применяющего код.
            base_amount: Базовая цена подписки (до скидки).

        Returns
            SPromoValidationResult: Данные промокода и рассчитанная скидка.

        Raises
            PromoCodeNotFoundError: Код с таким значением не существует.
            PromoCodeInactiveError: Код деактивирован либо вне срока действия.
            PromoCodeLimitReachedError: Лимит применений исчерпан.
            PromoCodeAlreadyUsedError: Этот пользователь уже применял код.

        """
        normalized_code = code.strip().upper()
        promo = await PromoCodeDAO.find_one_or_none(
            session=session, filters=SPromoCodeFilter(code=normalized_code)
        )
        if promo is None:
            raise PromoCodeNotFoundError(code=normalized_code)

        if not promo.is_active:
            raise PromoCodeInactiveError(code=normalized_code, reason="отключён")

        now = datetime.now(tz=settings_api.core.tzinfo)
        if promo.valid_from is not None and now < promo.valid_from:
            raise PromoCodeInactiveError(
                code=normalized_code, reason="пока не действует"
            )
        if promo.valid_until is not None and now > promo.valid_until:
            raise PromoCodeInactiveError(code=normalized_code, reason="срок истёк")

        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            raise PromoCodeLimitReachedError(
                code=normalized_code, max_uses=promo.max_uses
            )

        already_used = await PromoCodeUsageDAO.find_one_or_none(
            session=session,
            filters=SPromoUsageFilter(promo_code_id=promo.id, user_id=user_id),
        )
        if already_used is not None:
            raise PromoCodeAlreadyUsedError(code=normalized_code, user_id=user_id)

        discount_amount, final_amount = self._calculate_discount(promo, base_amount)
        logger.info(
            "[SERVICE] Промокод {} применим: user_id={} base_amount={} discount={} final={}",
            normalized_code,
            user_id,
            base_amount,
            discount_amount,
            final_amount,
        )
        return SPromoValidationResult(
            promo_code_id=promo.id,
            code=promo.code,
            discount_type=promo.discount_type,
            discount_value=promo.discount_value,
            base_amount=base_amount,
            discount_amount=discount_amount,
            final_amount=final_amount,
        )

    async def redeem_usage(
        self,
        session: AsyncSession,
        promo_code_id: int,
        user_id: int,
        transaction_id: UUID,
        discount_amount: int,
    ) -> None:
        """Фиксирует подтверждённое применение промокода.

        Вызывается только при переходе транзакции в статус `PAID` —
        деньги уже получены, поэтому неудача здесь (гонка параллельных
        подтверждений одного лимитированного кода) не должна откатывать
        уже состоявшуюся оплату и активацию подписки: такую гонку
        проигравшая сторона уже оплатила по честной скидочной цене,
        поэтому отказ был бы хуже, чем разовое превышение лимита на одно
        применение. Обе аномалии только логируются как warning — для
        финансового ревью, без прерывания потока оплаты.

        Args:
            session: Асинхронная SQLAlchemy-сессия (общая с транзакцией
                оплаты — применение промокода коммитится вместе с ней).
            promo_code_id: ID применяемого промокода.
            user_id: ID пользователя, применившего код.
            transaction_id: ID оплаченной транзакции.
            discount_amount: Сумма скидки, зафиксированная на транзакции.

        """
        try:
            async with session.begin_nested():
                await PromoCodeUsageDAO.add(
                    session=session,
                    values=SPromoCodeUsageCreate(
                        promo_code_id=promo_code_id,
                        user_id=user_id,
                        transaction_id=transaction_id,
                        discount_amount=discount_amount,
                        used_at=datetime.now(tz=settings_api.core.tzinfo),
                    ),
                )
        except IntegrityError:
            logger.warning(
                "[SERVICE] Повторная фиксация применения промокода id={} "
                "user_id={} transaction_id={} — запись уже существует (гонка), "
                "подписка по транзакции активируется без повторного учёта",
                promo_code_id,
                user_id,
                transaction_id,
            )
            return

        incremented = await PromoCodeDAO.try_increment_usage(
            session=session, promo_code_id=promo_code_id
        )
        if not incremented:
            logger.warning(
                "[SERVICE] Лимит применений промокода id={} достигнут в момент "
                "подтверждения оплаты (гонка) transaction_id={} — оплата уже "
                "принята, лимит превышен на одно применение",
                promo_code_id,
                transaction_id,
            )
