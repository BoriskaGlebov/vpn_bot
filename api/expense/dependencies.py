from api.expense.services import ExpenseService


def get_expense_service() -> ExpenseService:
    """Возвращает экземпляр ExpenseService."""
    return ExpenseService()
