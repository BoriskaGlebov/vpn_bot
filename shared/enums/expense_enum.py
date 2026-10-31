from enum import StrEnum


class ExpenseCategory(StrEnum):
    """Категория расхода.

    Attributes
        SERVER: Оплата серверов и VPS.
        DOMAIN: Регистрация и продление доменов.
        IP_ADDRESS: Аренда дополнительных IP-адресов.
        AI_LLM: Использование AI/LLM-сервисов.
        ADVERTISING: Рекламные расходы.
        OTHER: Прочие расходы, не попадающие в другие категории.

    """

    SERVER = "server"
    DOMAIN = "domain"
    IP_ADDRESS = "ip_address"
    AI_LLM = "ai_llm"
    ADVERTISING = "advertising"
    OTHER = "other"
