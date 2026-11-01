from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.enums.expense_enum import ExpenseCategory


class SExpenseCreate(BaseModel):
    """Данные для создания записи о расходе.

    Attributes
        amount (int): Сумма расхода в рублях (больше нуля).
        category (ExpenseCategory): Категория расхода.
        description (str | None): Произвольное описание.
        period_start (date): Начало периода расхода.
        period_end (date | None): Конец периода (None для разовых расходов).
        node_name (str | None): Имя VPN-ноды, если расход привязан к ноде.
        is_recurring (bool): Признак периодического расхода.

    """

    amount: int = Field(..., gt=0)
    category: ExpenseCategory
    description: str | None = None
    period_start: date
    period_end: date | None = None
    node_name: str | None = Field(None, max_length=64)
    is_recurring: bool = True


class SExpenseUpdate(BaseModel):
    """Данные для частичного обновления записи о расходе (PATCH).

    Все поля опциональны — передаются только изменяемые значения.

    Attributes
        amount (int | None): Новая сумма расхода в рублях.
        category (ExpenseCategory | None): Новая категория.
        description (str | None): Новое описание.
        period_start (date | None): Новая дата начала периода.
        period_end (date | None): Новая дата конца периода.
        node_name (str | None): Новое имя ноды.
        is_recurring (bool | None): Новый признак периодичности.

    """

    amount: int | None = Field(None, gt=0)
    category: ExpenseCategory | None = None
    description: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    node_name: str | None = Field(None, max_length=64)
    is_recurring: bool | None = None


class SExpenseRead(BaseModel):
    """Полные данные записи о расходе (ответ API).

    Attributes
        id (int): Уникальный идентификатор.
        amount (int): Сумма расхода в рублях.
        category (ExpenseCategory): Категория расхода.
        description (str | None): Описание.
        period_start (date): Начало периода.
        period_end (date | None): Конец периода.
        node_name (str | None): Имя ноды.
        is_recurring (bool): Признак периодичности.
        created_at (datetime): Дата и время создания записи.
        updated_at (datetime): Дата и время последнего обновления.

    """

    id: int
    amount: int
    category: ExpenseCategory
    description: str | None
    period_start: date
    period_end: date | None
    node_name: str | None
    is_recurring: bool
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class SExpenseFilter(BaseModel):
    """Фильтр поиска расходов по полям равенства.

    Используется с BaseDAO._build_filters (только операторы ==).

    Attributes
        id (int | None): Фильтр по ID.
        category (ExpenseCategory | None): Фильтр по категории.
        node_name (str | None): Фильтр по имени ноды.

    """

    id: int | None = None
    category: ExpenseCategory | None = None
    node_name: str | None = None


class SMonthlyExpenseSummary(BaseModel):
    """Сводка расходов за один месяц.

    Attributes
        month (str): Месяц в формате 'YYYY-MM'.
        total (int): Суммарный расход за месяц в рублях.

    """

    month: str
    total: int
