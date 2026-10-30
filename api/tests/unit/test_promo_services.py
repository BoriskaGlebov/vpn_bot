"""Тесты PromoService: проверка применимости и фиксация применения промокода.

Используется реальная (sqlite) сессия из conftest, а не mock_session —
`redeem_usage` опирается на настоящее поведение БД (уникальный констрейнт,
begin_nested/IntegrityError, атомарный инкремент), которое мок не воспроизводит.
"""

import uuid
from datetime import datetime, timedelta

import pytest

from api.app_error.base_error import (
    PromoCodeAlreadyUsedError,
    PromoCodeInactiveError,
    PromoCodeLimitReachedError,
    PromoCodeNotFoundError,
)
from api.core.config import settings_api
from api.promo.dao import PromoCodeUsageDAO
from api.promo.models import PromoCode, PromoCodeUsage
from api.promo.schemas import SPromoUsageFilter
from api.promo.services import PromoService
from api.users.dao import UserDAO
from api.users.schemas import SRole, SUser
from shared.enums.admin_enum import RoleEnum
from shared.enums.promo_enum import PromoDiscountType


@pytest.fixture
def promo_service() -> PromoService:
    return PromoService()


async def make_user(session, telegram_id: int):
    """Создаёт минимального пользователя для тестов применения промокода."""
    user = await UserDAO.add_role_subscription(
        session=session,
        values_user=SUser(telegram_id=telegram_id, username=f"user{telegram_id}"),
        values_role=SRole(name=RoleEnum.USER),
    )
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_validate_code_not_found(promo_service, session):
    """Код, которого нет в БД — PromoCodeNotFoundError."""
    user = await make_user(session, 1)

    with pytest.raises(PromoCodeNotFoundError):
        await promo_service.validate_code(
            session=session, code="NOPE", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_inactive(promo_service, session):
    """Код деактивирован администратором — PromoCodeInactiveError."""
    user = await make_user(session, 2)
    promo = PromoCode(
        code="OFF10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        is_active=False,
    )
    session.add(promo)
    await session.flush()

    with pytest.raises(PromoCodeInactiveError):
        await promo_service.validate_code(
            session=session, code="off10", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_expired(promo_service, session):
    """Код вне срока действия (valid_until в прошлом) — PromoCodeInactiveError."""
    user = await make_user(session, 3)
    promo = PromoCode(
        code="OLD10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        valid_until=datetime.now(tz=settings_api.core.tzinfo) - timedelta(days=1),
    )
    session.add(promo)
    await session.flush()

    with pytest.raises(PromoCodeInactiveError):
        await promo_service.validate_code(
            session=session, code="OLD10", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_not_yet_valid(promo_service, session):
    """Код с valid_from в будущем пока не действует — PromoCodeInactiveError."""
    user = await make_user(session, 4)
    promo = PromoCode(
        code="FUTURE10",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        valid_from=datetime.now(tz=settings_api.core.tzinfo) + timedelta(days=1),
    )
    session.add(promo)
    await session.flush()

    with pytest.raises(PromoCodeInactiveError):
        await promo_service.validate_code(
            session=session, code="FUTURE10", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_limit_reached(promo_service, session):
    """Лимит применений уже исчерпан — PromoCodeLimitReachedError."""
    user = await make_user(session, 5)
    promo = PromoCode(
        code="MAXED",
        discount_type=PromoDiscountType.FIXED,
        discount_value=50,
        max_uses=1,
        used_count=1,
    )
    session.add(promo)
    await session.flush()

    with pytest.raises(PromoCodeLimitReachedError):
        await promo_service.validate_code(
            session=session, code="MAXED", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_already_used_by_user(promo_service, session):
    """Пользователь, уже применявший код ранее — PromoCodeAlreadyUsedError."""
    user = await make_user(session, 6)
    promo = PromoCode(
        code="ONCE",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
    )
    session.add(promo)
    await session.flush()
    session.add(
        PromoCodeUsage(
            promo_code_id=promo.id,
            user_id=user.id,
            transaction_id=uuid.uuid4(),
            discount_amount=10,
            used_at=datetime.now(),
        )
    )
    await session.flush()

    with pytest.raises(PromoCodeAlreadyUsedError):
        await promo_service.validate_code(
            session=session, code="ONCE", user_id=user.id, base_amount=100
        )


@pytest.mark.asyncio
async def test_validate_code_percent_discount(promo_service, session):
    """Процентная скидка считается от базовой суммы."""
    user = await make_user(session, 7)
    promo = PromoCode(
        code="PERCENT20",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=20,
    )
    session.add(promo)
    await session.flush()

    result = await promo_service.validate_code(
        session=session, code="percent20", user_id=user.id, base_amount=100
    )

    assert result.promo_code_id == promo.id
    assert result.code == "PERCENT20"
    assert result.discount_amount == 20
    assert result.final_amount == 80


@pytest.mark.asyncio
async def test_validate_code_fixed_discount(promo_service, session):
    """Фиксированная скидка вычитается рублями."""
    user = await make_user(session, 8)
    promo = PromoCode(
        code="FIXED30",
        discount_type=PromoDiscountType.FIXED,
        discount_value=30,
    )
    session.add(promo)
    await session.flush()

    result = await promo_service.validate_code(
        session=session, code="FIXED30", user_id=user.id, base_amount=100
    )

    assert result.discount_amount == 30
    assert result.final_amount == 70


@pytest.mark.asyncio
async def test_validate_code_discount_clamped_to_min_final_amount(
    promo_service, session
):
    """Скидка не может увести итоговую сумму в ноль или минус."""
    user = await make_user(session, 9)
    promo = PromoCode(
        code="HUGE",
        discount_type=PromoDiscountType.FIXED,
        discount_value=1000,
    )
    session.add(promo)
    await session.flush()

    result = await promo_service.validate_code(
        session=session, code="HUGE", user_id=user.id, base_amount=100
    )

    assert result.final_amount == 1
    assert result.discount_amount == 99


@pytest.mark.asyncio
async def test_redeem_usage_increments_counter_and_creates_record(
    promo_service, session
):
    """Успешная фиксация применения: записывается usage и растёт used_count."""
    user = await make_user(session, 10)
    promo = PromoCode(
        code="REDEEM1",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
        max_uses=5,
        used_count=0,
    )
    session.add(promo)
    await session.flush()
    transaction_id = uuid.uuid4()

    await promo_service.redeem_usage(
        session=session,
        promo_code_id=promo.id,
        user_id=user.id,
        transaction_id=transaction_id,
        discount_amount=15,
    )

    await session.refresh(promo)
    assert promo.used_count == 1

    usage = await PromoCodeUsageDAO.find_one_or_none(
        session=session,
        filters=SPromoUsageFilter(promo_code_id=promo.id, user_id=user.id),
    )
    assert usage is not None
    assert usage.transaction_id == transaction_id
    assert usage.discount_amount == 15


@pytest.mark.asyncio
async def test_redeem_usage_duplicate_does_not_raise(promo_service, session):
    """Повторная фиксация того же (promo_code_id, user_id) не роняет flow оплаты.

    Гонка: два параллельных подтверждения оплаты одного пользователя с
    одним кодом. Деньги по обеим транзакциям уже получены, поэтому сервис
    не должен поднимать исключение — только залогировать аномалию.
    """
    user = await make_user(session, 11)
    promo = PromoCode(
        code="RACE1",
        discount_type=PromoDiscountType.PERCENT,
        discount_value=10,
    )
    session.add(promo)
    await session.flush()

    await promo_service.redeem_usage(
        session=session,
        promo_code_id=promo.id,
        user_id=user.id,
        transaction_id=uuid.uuid4(),
        discount_amount=10,
    )
    await session.flush()
    used_count_after_first = promo.used_count

    # Второе применение тем же пользователем — другая транзакция, тот же
    # (promo_code_id, user_id), что нарушает uq_promo_usage_user.
    await promo_service.redeem_usage(
        session=session,
        promo_code_id=promo.id,
        user_id=user.id,
        transaction_id=uuid.uuid4(),
        discount_amount=10,
    )

    await session.refresh(promo)
    # Счётчик не увеличивается повторно — только одно реальное применение
    # дошло до записи в usages.
    assert promo.used_count == used_count_after_first


@pytest.mark.asyncio
async def test_redeem_usage_limit_race_does_not_raise(promo_service, session):
    """Гонка на лимите применений: инкремент не проходит, но flow не падает.

    Тут гонка двух РАЗНЫХ пользователей за последний слот лимитированного
    кода (max_uses=1), и у обоих уже прошла реальная оплата.
    """
    user_a = await make_user(session, 12)
    user_b = await make_user(session, 13)
    promo = PromoCode(
        code="LASTSLOT",
        discount_type=PromoDiscountType.FIXED,
        discount_value=10,
        max_uses=1,
        used_count=0,
    )
    session.add(promo)
    await session.flush()

    await promo_service.redeem_usage(
        session=session,
        promo_code_id=promo.id,
        user_id=user_a.id,
        transaction_id=uuid.uuid4(),
        discount_amount=10,
    )

    # Второй пользователь проигрывает гонку за лимит, но его оплата уже
    # прошла — redeem_usage не должен бросать исключение.
    await promo_service.redeem_usage(
        session=session,
        promo_code_id=promo.id,
        user_id=user_b.id,
        transaction_id=uuid.uuid4(),
        discount_amount=10,
    )

    usage_b = await PromoCodeUsageDAO.find_one_or_none(
        session=session,
        filters=SPromoUsageFilter(promo_code_id=promo.id, user_id=user_b.id),
    )
    # Запись об использовании всё равно создаётся (для статистики/истории) —
    # только счётчик лимита не превышает единицу сверх допустимого.
    assert usage_b is not None
    await session.refresh(promo)
    assert promo.used_count == 1
