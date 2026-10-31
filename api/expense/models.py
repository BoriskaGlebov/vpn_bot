from datetime import date

from sqlalchemy import Date
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from api.core.database import Base, int_pk
from shared.enums.expense_enum import ExpenseCategory


class Expense(Base):
    """Расход на инфраструктуру или операционную деятельность.

    Attributes
        id (int): Уникальный идентификатор записи.
        amount (int): Сумма расхода в рублях.
        category (ExpenseCategory): Категория расхода (сервер, домен и т.д.).
        description (str | None): Произвольное описание расхода.
        period_start (date): Начало периода, к которому относится расход.
        period_end (date | None): Конец периода (None для разовых расходов).
        node_name (str | None): Имя VPN-ноды, если расход привязан к конкретной ноде.
        is_recurring (bool): Признак периодического (регулярного) расхода.

    """

    id: Mapped[int_pk]
    amount: Mapped[int] = mapped_column(nullable=False)
    category: Mapped[ExpenseCategory] = mapped_column(
        SQLEnum(ExpenseCategory), index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    node_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(default=True, server_default="true")

    def __str__(self) -> str:
        """Возвращает краткое строковое представление расхода."""
        return f"{self.category} {self.amount}₽ ({self.period_start})"
