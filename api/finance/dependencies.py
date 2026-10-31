from api.finance.services import FinanceService


def get_finance_service() -> FinanceService:
    """Возвращает экземпляр FinanceService."""
    return FinanceService()
