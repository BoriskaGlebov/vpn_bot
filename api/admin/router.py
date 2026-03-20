from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from api.admin.dependencies import get_admin_service
from api.admin.enums import RoleEnum
from api.admin.services import AdminService
from api.core.dependencies import get_session
from shared.schemas.admin import SChangeRole, SExtendSubscription
from shared.schemas.users import SUserOut

router = APIRouter(prefix="/admin", tags=["bot"])


@router.get(
    "/users/{telegram_id}",
    response_model=SUserOut,
    status_code=status.HTTP_200_OK,
    summary="Получить пользователя по Telegram ID",
    description="Возвращает пользователя по его Telegram ID. "
    "Если пользователь не найден — возвращается ошибка 404.",
    responses={
        200: {
            "description": "Пользователь успешно найден",
        },
        404: {
            "description": "Пользователь не найден",
            "content": {
                "application/json": {
                    "example": {"detail": "Пользователь с telegram_id=123 не найден"}
                }
            },
        },
    },
)
async def get_user(
    telegram_id: int,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
) -> SUserOut:
    """Получает пользователя по Telegram ID.

    Выполняет поиск пользователя в системе по его уникальному
    Telegram ID.

    В случае отсутствия пользователя выбрасывается исключение
    `UserNotFoundError`, которое обрабатывается глобальным
    обработчиком и преобразуется в HTTP 404.

    Args:
        telegram_id (int): Уникальный идентификатор пользователя в Telegram.
        session (AsyncSession): Асинхронная сессия базы данных.
        service (AdminService): Сервис для работы с пользователями.

    Returns
        SUserOut: Данные пользователя.

    Raises
        UserNotFoundError: Если пользователь с указанным Telegram ID не найден.

    """
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
)
async def get_users(
    filter_type: RoleEnum = Query(
        default=RoleEnum.USER,
        description="Фильтр пользователей по роли",
    ),
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
) -> list[SUserOut]:
    """Получает список пользователей по фильтру ролей.

    Выполняет выборку пользователей в зависимости от указанного
    типа фильтра. Если фильтр не задан, возвращаются все пользователи.

    Args:
        filter_type (RoleEnum): Тип фильтра пользователей:
            - ALL — все пользователи
            - USER — обычные пользователи
            - ADMIN — администраторы
            - FOUNDER — владельцы системы
        session (AsyncSession): Асинхронная сессия базы данных.
        service (AdminService): Сервис для работы с пользователями.

    Returns
        list[SUserOut]: Список пользователей, соответствующих фильтру.

    """
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
        200: {
            "description": "Роль пользователя успешно изменена",
        },
        404: {
            "description": "Пользователь или роль не найдены",
            "content": {
                "application/json": {
                    "example": {"detail": "Пользователь с telegram_id=123 не найден"}
                }
            },
        },
    },
)
async def change_user_role(
    data: SChangeRole,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
) -> SUserOut:
    """Изменяет роль пользователя.

    Выполняет изменение роли пользователя по его Telegram ID.
    Входные данные валидируются через Enum, что гарантирует
    корректность передаваемой роли.

    В случае отсутствия пользователя или роли выбрасывается
    исключение `UserNotFoundError`, которое преобразуется
    в HTTP 404 через глобальный обработчик.

    Args:
        data (SChangeRole): Данные для изменения роли:
            - telegram_id — ID пользователя
            - role_name — новая роль (user, admin, founder)
        session (AsyncSession): Асинхронная сессия базы данных.
        service (AdminService): Сервис управления пользователями.

    Returns
        SUserOut: Обновлённые данные пользователя.

    Raises
        UserNotFoundError: Если пользователь или роль не найдены.

    """
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
        200: {
            "description": "Подписка успешно продлена",
        },
        404: {
            "description": "Пользователь не найден",
            "content": {
                "application/json": {
                    "example": {"detail": "Пользователь с telegram_id=123 не найден"}
                }
            },
        },
    },
)
async def extend_subscription(
    data: SExtendSubscription,
    session: AsyncSession = Depends(get_session),
    service: AdminService = Depends(get_admin_service),
) -> SUserOut:
    """Продлевает подписку пользователя.

    Выполняет продление активной подписки пользователя на указанное
    количество месяцев.

    Алгоритм работы:
    - ищет пользователя по Telegram ID
    - проверяет наличие активной подписки
    - продлевает подписку через сервисный слой
    - возвращает обновлённые данные пользователя

    Args:
        data (SExtendSubscription): Данные запроса:
            - telegram_id: ID пользователя в Telegram
            - months: количество месяцев продления
        session (AsyncSession): Асинхронная сессия базы данных
        service (AdminService): сервис бизнес-логики

    Returns
        SUserOut: Обновлённая информация о пользователе

    Raises
        UserNotFoundError: Если пользователь не найден
        SubscriptionNotFoundError: Подписка не активна

    """
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
