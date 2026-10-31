from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import ExpenseNotFoundError, InvalidNodeNameError
from api.core.config import settings_api
from api.expense.dao import ExpenseDAO
from api.expense.models import Expense
from api.expense.schemas import (
    SExpenseCreate,
    SExpenseFilter,
    SExpenseUpdate,
    SMonthlyExpenseSummary,
)


class ExpenseService:
    """Сервис управления расходами.

    Обеспечивает CRUD-операции над записями о расходах и агрегацию
    по месяцам для аналитики. Все операции выполняются в рамках
    переданной сессии — коммит на вызывающей стороне.
    """

    @staticmethod
    def _validate_node_name(node_name: str | None) -> None:
        """Проверяет, что имя ноды присутствует в конфиге vpn.nodes.

        Если `vpn_node_names` пустое (тесты, минимальный конфиг без секции
        [vpn.nodes]) — валидация пропускается.

        Args:
            node_name: Имя ноды для проверки, или None (проверка не нужна).

        Raises
            InvalidNodeNameError: Имя ноды не найдено в конфигурации.

        """
        if node_name is None:
            return
        known = settings_api.vpn_node_names
        if known and node_name not in known:
            raise InvalidNodeNameError(node_name=node_name, known=known)

    async def create(self, session: AsyncSession, data: SExpenseCreate) -> Expense:
        """Создаёт новую запись о расходе.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            data: Данные для создания.

        Returns
            Expense: Созданная запись.

        """
        self._validate_node_name(data.node_name)
        expense = await ExpenseDAO.add(session=session, values=data)
        logger.info(
            "[SERVICE] Создан расход id={} category={} amount={}",
            expense.id,
            expense.category,
            expense.amount,
        )
        return expense

    async def get_by_id(self, session: AsyncSession, expense_id: int) -> Expense:
        """Возвращает расход по ID или бросает 404.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            expense_id: ID записи.

        Returns
            Expense: Найденная запись.

        Raises
            ExpenseNotFoundError: Если запись с таким ID не существует.

        """
        expense = await ExpenseDAO.find_one_or_none_by_id(
            data_id=expense_id, session=session
        )
        if expense is None:
            raise ExpenseNotFoundError(expense_id=expense_id)
        return expense

    async def get_all(
        self,
        session: AsyncSession,
        filters: SExpenseFilter | None = None,
    ) -> list[Expense]:
        """Возвращает список расходов, опционально фильтруя по полям равенства.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            filters: Фильтры по полям (category, node_name, id). None — без фильтрации.

        Returns
            list[Expense]: Список найденных записей.

        """
        if filters is None:
            filters = SExpenseFilter()
        return await ExpenseDAO.find_all(session=session, filters=filters)

    async def update(
        self,
        session: AsyncSession,
        expense_id: int,
        data: SExpenseUpdate,
    ) -> Expense:
        """Обновляет запись о расходе (PATCH — только переданные поля).

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            expense_id: ID обновляемой записи.
            data: Новые значения полей (только непустые применяются).

        Returns
            Expense: Обновлённая запись.

        Raises
            ExpenseNotFoundError: Если запись с таким ID не существует.

        """
        expense = await self.get_by_id(session=session, expense_id=expense_id)
        self._validate_node_name(data.node_name)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(expense, field, value)
        await session.flush()
        await session.refresh(expense)
        logger.info("[SERVICE] Обновлён расход id={}", expense_id)
        return expense

    async def delete(self, session: AsyncSession, expense_id: int) -> None:
        """Удаляет запись о расходе.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            expense_id: ID удаляемой записи.

        Raises
            ExpenseNotFoundError: Если запись с таким ID не существует.

        """
        await self.get_by_id(session=session, expense_id=expense_id)
        await ExpenseDAO.delete(session=session, filters=SExpenseFilter(id=expense_id))
        logger.info("[SERVICE] Удалён расход id={}", expense_id)

    async def get_monthly_summary(
        self,
        session: AsyncSession,
        year: int,
    ) -> list[SMonthlyExpenseSummary]:
        """Возвращает суммарные расходы по месяцам за указанный год.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год агрегации.

        Returns
            list[SMonthlyExpenseSummary]: Список месячных сводок
            в порядке возрастания месяца.

        """
        rows = await ExpenseDAO.get_monthly_totals(session=session, year=year)
        return [
            SMonthlyExpenseSummary(month=month, total=total) for month, total in rows
        ]
