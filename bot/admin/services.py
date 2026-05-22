from loguru import logger

from bot.admin.adapter import AdminAPIAdapter
from bot.admin.enums import AdminModeKeys
from bot.admin.schemas import SChangeRole, SExtendSubscription, SYearIncome
from bot.users.router import m_admin
from bot.users.schemas import (
    SUserOut,
)
from shared.enums.admin_enum import RoleEnum


class AdminService:
    """Сервис бизнес-логики управления пользователями.

    Обеспечивает взаимодействие между Telegram-ботом и Admin API.
    Выполняет orchestration (сборку payload, форматирование данных),
    не содержит работы с БД.
    """

    def __init__(self, adapter: AdminAPIAdapter) -> None:
        """Инициализирует сервис.

        Args:
            adapter (AdminAPIAdapter): API адаптер для работы с backend.

        """
        self.api_adapter = adapter

    async def get_user_by_telegram_id(self, telegram_id: int) -> SUserOut:
        """Получает пользователя по Telegram ID.

        Args:
            telegram_id (int): Уникальный идентификатор пользователя.

        Returns
            SUserOut: Данные пользователя.

        """
        logger.info("Получение пользователя telegram_id=%s", telegram_id)

        user = await self.api_adapter.get_user_by_telegram_id(telegram_id)

        logger.debug("Пользователь получен telegram_id=%s", telegram_id)

        return user

    async def get_users_by_filter(self, filter_type: RoleEnum) -> list[SUserOut]:
        """Получает список пользователей по роли.

        Args:
            filter_type (RoleEnum): Фильтр пользователей.

        Returns
            list[SUserOut]: Список пользователей.

        """
        logger.info("Получение пользователей по роли=%s", filter_type)

        users = await self.api_adapter.get_users(filter_type)

        logger.debug("Найдено пользователей: %s", len(users))

        return users

    @classmethod
    async def format_user_text(
        cls, suser: SUserOut, key: str = AdminModeKeys.USER
    ) -> str:
        """Форматирует текст пользователя для сообщений.

        Args:
            suser (SUserOut): Схема пользователя.
            key (str): Ключ шаблона текста в `m_admin`.

        Returns
            str: Отформатированный текст пользователя.

        """
        template: str = m_admin[key]
        config_str = "\n".join(
            [f"📌 {config.file_name}" for config in suser.vpn_configs]
        )
        return template.format(
            first_name=suser.first_name or "-",
            last_name=suser.last_name or "-",
            username=suser.username or "-",
            telegram_id=suser.telegram_id or "-",
            roles=str(suser.role),
            subscription=str(suser.current_subscription) or "-",
            config_files=(
                f"📜 <b>Пользовательские конфиги:</b>\n {config_str}"
                if suser.vpn_configs
                else ""
            ),
        )

    async def change_user_role(self, telegram_id: int, role_name: RoleEnum) -> SUserOut:
        """Изменяет роль пользователя.

        Args:
            telegram_id (int): Telegram ID пользователя.
            role_name (RoleEnum): Новая роль.

        Returns
            SUserOut: Обновлённые данные пользователя.

        """
        logger.info(
            "Изменение роли пользователя telegram_id=%s role=%s",
            telegram_id,
            role_name,
        )

        payload = SChangeRole(
            telegram_id=telegram_id,
            role_name=role_name,
        )

        user = await self.api_adapter.change_user_role(payload)

        logger.success(
            "Роль изменена telegram_id=%s role=%s",
            telegram_id,
            role_name,
        )

        return user

    async def extend_user_subscription(self, telegram_id: int, months: int) -> SUserOut:
        """Продлевает подписку пользователя.

        Args:
            telegram_id (int): Telegram ID пользователя.
            months (int): Количество месяцев продления.

        Returns
            SUserOut: Обновлённый пользователь.

        """
        logger.info(
            "Продление подписки telegram_id=%s months=%s",
            telegram_id,
            months,
        )

        payload = SExtendSubscription(
            telegram_id=telegram_id,
            months=months,
        )

        user: SUserOut = await self.api_adapter.extend_subscription(payload)

        logger.success(
            "Подписка продлена telegram_id=%s months=%s",
            telegram_id,
            months,
        )

        return user

    async def year_income(self) -> SYearIncome:
        """Получает доход за текущий год.

        Returns
            SYearIncome: Данные о годовом доходе.

        """
        logger.info("Запрос годового дохода")

        res = await self.api_adapter.year_income()

        logger.debug("Годовой доход получен: %s", res.year_income)

        return res
