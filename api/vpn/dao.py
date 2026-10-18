from dataclasses import dataclass

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    SubscriptionNotFoundError,
    VPNLimitError,
)
from api.core.dao.base import BaseDAO
from api.subscription.models import DEVICE_LIMITS
from api.users.models import User
from api.vpn.models import VPNConfig, VPNConfigStatus
from api.vpn.schemas import SVPNUserConfigsFilter


@dataclass(frozen=True)
class VPNLimitStatus:
    """Результат проверки лимита VPN-конфигов пользователя.

    Attributes
        can_add (bool): Может ли пользователь добавить ещё один конфиг.
        limit (int): Лимит устройств, который был применён.
        current (int): Текущее количество активных конфигов.

    """

    can_add: bool
    limit: int
    current: int


class VPNConfigDAO(BaseDAO[VPNConfig]):
    """DAO для работы с VPN-конфигами пользователей."""

    model = VPNConfig

    @classmethod
    async def get_limit_status(
        cls, session: AsyncSession, user: User
    ) -> VPNLimitStatus:
        """Считает лимит устройств пользователя — единая точка для всех вызывающих.

        Пользователь передаётся уже загруженным (с подпиской) — метод не
        перечитывает его из БД и поэтому не может столкнуться с
        "пользователь не найден"; эта проверка — забота вызывающего. Это
        единственное место, которое считает `current`/`limit`/`can_add`,
        поэтому `check_limit` и `add_config` не могут разойтись в счёте
        (см. #269). Считаются только конфиги со статусом `ACTIVE` —
        `PENDING_DELETE`/`DELETED` не занимают слот.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Уже загруженный пользователь (с `current_subscription`).

        Raises
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.

        Returns
            VPNLimitStatus: Текущее количество, лимит и возможность добавить конфиг.

        """
        if not user.current_subscription or not user.current_subscription.is_active:
            logger.warning("Нет активной подписки: user_id={}", user.id)
            raise SubscriptionNotFoundError(user_id=user.id, username=user.username)

        current = await cls.count(
            session=session,
            filters=SVPNUserConfigsFilter(
                user_id=user.id, status=VPNConfigStatus.ACTIVE
            ),
        )
        sub_type = user.current_subscription.type
        limit = DEVICE_LIMITS.get(sub_type, 0) if sub_type else 0
        logger.debug(
            f"[DAO] Лимит конфигов для пользователя {user.id} "
            f"({user.current_subscription.type}): {current}/{limit}",
        )
        return VPNLimitStatus(can_add=current < limit, limit=limit, current=current)

    @classmethod
    async def add_config(
        cls,
        session: AsyncSession,
        user: User,
        file_name: str,
        pub_key: str,
        node_name: str | None = None,
        backend: str | None = None,
        protocol: str | None = None,
        config_ids: list[str] | None = None,
    ) -> VPNConfig:
        """Создаёт новый VPN конфиг для пользователя.

        Проверяет лимит конфигов, добавляет запись в базу и возвращает объект.

        Args:
            session (AsyncSession): Асинхронная сессия SQLAlchemy.
            user (User): Уже загруженный пользователь (с `current_subscription`).
            file_name (str): Название файла конфигурации.
            pub_key (str): Публичный ключ пользователя.
            node_name (str | None): Имя ноды/локации.
            backend (str | None): Бэкенд конфига ("amnezia" | "xray").
            protocol (str | None): Конкретный протокол/версия внутри бэкенда.
            config_ids (list[str] | None): Для XRay — uuid клиентов на панели.

        Raises
            SubscriptionNotFoundError: Если у пользователя нет активной подписки.
            VPNLimitError: Если пользователь достиг лимита конфигов.

        Returns
            VPNConfig: Созданный объект VPN-конфига.

        """
        logger.info(
            f"[DAO] Попытка создать новый VPN конфиг для пользователя {user.id}: файл='{file_name}'",
        )
        try:
            status = await cls.get_limit_status(session=session, user=user)
            if not status.can_add:
                # Ожидаемое бизнес-ограничение (превышен лимит устройств),
                # а не системная ошибка. limit — именно тот, что применялся
                # в сравнении выше, а не настройка по умолчанию (см. #269).
                logger.warning(
                    f"[DAO] Создание конфига отклонено — пользователь {user.id} "
                    f"достиг лимита {status.limit}",
                )
                raise VPNLimitError(
                    user_id=user.id,
                    limit=status.limit,
                    current=status.current,
                    username=user.username or "",
                )

            config = VPNConfig(
                user_id=user.id,
                file_name=file_name,
                pub_key=pub_key,
                node_name=node_name,
                backend=backend,
                protocol=protocol,
                config_ids=config_ids,
            )
            session.add(config)
            # flush до лога успеха — иначе config.id ещё None (см. #274,
            # тот же класс, что #233 у add_many).
            await session.flush()
            logger.success(
                f"[DAO] Создан новый VPNConfig id={config.id} для пользователя {user.id} (файл='{file_name}')",
            )
            return config
        except SQLAlchemyError:
            logger.exception("[DAO] Ошибка при добавлении конфиг файла")
            raise
