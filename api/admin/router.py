from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.admin.dependencies import check_admin_role, get_admin_service
from api.admin.schemas import SChangeRole, SExtendSubscription
from api.admin.services import AdminService
from api.core.dependencies import get_session
from api.core.exceptions.schema import APIErrorResponse
from api.core.openapi_responses import ADMIN_RESPONSES
from api.payment.dependencies import get_payment_service
from api.payment.schemas import SYearIncome
from api.payment.services import PaymentService
from api.users.models import User
from api.users.schemas import SUserOut
from shared.enums.admin_enum import RoleEnum

router = APIRouter(prefix="/admin", tags=["bot", "ADMIN"])


@router.get(
    "/users/{telegram_id}",
    response_model=SUserOut,
    status_code=status.HTTP_200_OK,
    summary="Получить пользователя по Telegram ID",
    description="Возвращает пользователя по его Telegram ID. "
    "Если пользователь не найден — возвращается ошибка 404.",
    responses={
        **ADMIN_RESPONSES,
        200: {
            "description": "Пользователь успешно найден",
        },
    },
)
async def get_user(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
    admin_auth: User = Depends(check_admin_role),
) -> SUserOut:
    """Получает пользователя по Telegram ID."""
    logger.info("Запрос пользователя по telegram_id={}", telegram_id)

    user = await service.get_user_by_telegram_id(
        session=session,
        telegram_id=telegram_id,
    )

    logger.success("Пользователь найден telegram_id={}", telegram_id)

    return user


@router.get(
    "/users",
    response_model=list[SUserOut],
    status_code=status.HTTP_200_OK,
    summary="Получить список пользователей по фильтру ролей",
    description=(
        "Возвращает список пользователей с возможностью фильтрации по ролям.\n\n"
        "Доступные значения фильтра:\n"
        "- `user` — обычные пользователи\n"
        "- `admin` — администраторы\n"
        "- `founder` — владельцы системы"
    ),
    responses=ADMIN_RESPONSES,
)
async def get_users(
    filter_type: RoleEnum = Query(
        default=RoleEnum.USER,
        description="Фильтр пользователей по роли",
    ),
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
    admin_auth: User = Depends(check_admin_role),
) -> list[SUserOut]:
    """Получает список пользователей по фильтру ролей."""
    logger.info("Запрос списка пользователей filter_type={}", filter_type.value)

    users = await service.get_users_by_filter(
        session=session,
        filter_type=filter_type,
    )

    logger.success(
        "Получен список пользователей filter_type={} count={}",
        filter_type.value,
        len(users),
    )

    return users


@router.patch(
    "/users/role",
    response_model=SUserOut,
    status_code=status.HTTP_200_OK,
    summary="Изменить роль пользователя",
    description=(
        "Изменяет роль пользователя по его Telegram ID.\n\n"
        "Доступные роли:\n"
        "- `user` — обычный пользователь\n"
        "- `admin` — администратор\n"
        "- `founder` — владелец системы\n\n"
        "Если пользователь или роль не найдены — возвращается ошибка 404."
    ),
    responses={
        **ADMIN_RESPONSES,
        200: {
            "description": "Роль пользователя успешно изменена",
        },
        404: {
            "model": APIErrorResponse,
            "description": "Пользователь или роль не найдены",
        },
    },
)
async def change_user_role(
    data: SChangeRole,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
    admin_auth: User = Depends(check_admin_role),
) -> SUserOut:
    """Изменяет роль пользователя."""
    logger.info(
        "Запрос на изменение роли telegram_id={} role={}",
        data.telegram_id,
        data.role_name.value,
    )
    user = await service.change_user_role(
        session=session,
        telegram_id=data.telegram_id,
        role_name=data.role_name,
    )

    logger.success(
        "Роль изменена telegram_id={} role={}",
        data.telegram_id,
        data.role_name.value,
    )

    return user


@router.patch(
    "/users/subscription",
    response_model=SUserOut,
    status_code=status.HTTP_200_OK,
    summary="Продлить подписку пользователя",
    description=(
        "Продлевает активную подписку пользователя по Telegram ID.\n\n"
        "Если пользователь не найден — возвращается ошибка 404.\n"
        "Если у пользователя нет активной подписки, она будет создана или обработана в сервисе."
    ),
    responses={
        **ADMIN_RESPONSES,
        200: {
            "description": "Подписка успешно продлена",
        },
        404: {
            "model": APIErrorResponse,
            "description": "Пользователь не найден или подписка не активна",
        },
    },
)
async def extend_subscription(
    data: SExtendSubscription,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
    admin_auth: User = Depends(check_admin_role),
) -> SUserOut:
    """Продлевает подписку пользователя."""
    logger.info(
        "Запрос продления подписки telegram_id={} months={}",
        data.telegram_id,
        data.months,
    )

    user = await service.extend_user_subscription(
        session=session,
        telegram_id=data.telegram_id,
        months=data.months,
    )

    logger.success(
        "Подписка продлена telegram_id={} months={}",
        data.telegram_id,
        data.months,
    )

    return user


@router.get(
    "/analytics/income",
    response_model=SYearIncome,
    status_code=status.HTTP_200_OK,
    summary="Получить аналитику дохода за год",
    description=(
        "Возвращает аналитику доходов за указанный год.\n\n"
        "Если год не передан, используется текущий год.\n"
        "В ответе содержится информация о доходе по месяцам "
        "и общая сумма дохода за год."
    ),
    responses={
        **ADMIN_RESPONSES,
        200: {
            "description": "Аналитика дохода успешно получена",
        },
    },
)
async def get_income(
    year: int | None = None,
    service: PaymentService = Depends(get_payment_service),
    session: AsyncSession = Depends(get_session),
    admin_auth: User = Depends(check_admin_role),
) -> SYearIncome:
    """Получает аналитику доходов за год."""
    logger.info("Запрос аналитики дохода year={} admin_id={}", year, admin_auth.id)

    income = await service.get_year_income(session=session, year=year)

    logger.success("Аналитика дохода получена year={}", year)

    return income
