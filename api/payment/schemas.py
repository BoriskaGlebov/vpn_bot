from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from api.payment.model import PaymentSource, PaymentStatus
from api.referrals.schemas import GrantReferralBonusResponse
from api.users.schemas import SUserOut


class Currency(str, Enum):
    """Поддерживаемые валюты."""

    RUB = "RUB"


class SCreateManualPaymentTransaction(BaseModel):
    """Схема создания ручной платежной транзакции.

    Attributes
        amount: Сумма платежа в рублях (целое число, не копейки).
        currency: Код валюты по ISO 4217.
        subscription_months: Количество месяцев подписки.
        is_premium: Флаг премиум-подписки.
        is_founder: Флаг founder-статуса.
        description: Дополнительное описание платежа.

    """

    amount: int = Field(gt=0)
    currency: Currency = Currency.RUB
    subscription_months: int = Field(gt=0)
    is_premium: bool = False
    is_founder: bool = False

    description: str | None = None
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class SCreateTransaction(SCreateManualPaymentTransaction):
    """Схема создания платежной транзакции для конкретного пользователя.

    Attributes
        user_id: Идентификатор пользователя.

    """

    user_id: int

    model_config = ConfigDict(from_attributes=True)


class SPaymentTransactionResponse(BaseModel):
    """Ответ с данными платежной транзакции.

    Attributes
        id: UUID транзакции.
        user_id: ID пользователя.
        tg_id: Telegram ID пользователя.
        amount: Сумма платежа.
        currency: Код валюты.
        status: Статус платежа.
        source: Источник создания платежа.
        subscription_months: Количество месяцев подписки.
        is_premium: Флаг премиум-подписки.
        is_founder: Флаг founder-статуса.
        description: Описание платежа.
        created_by_admin_id: ID администратора, создавшего транзакцию.
        confirmed_by_admin_id: ID администратора, подтвердившего платеж.
        gateway_transaction_id: ID транзакции в платёжном шлюзе.
        confirmed_at: Дата подтверждения платежа.
        paid_at: Дата успешной оплаты.

    """

    id: UUID

    user_id: int
    tg_id: int

    amount: int
    currency: str

    status: PaymentStatus
    source: PaymentSource

    subscription_months: int
    is_premium: bool
    is_founder: bool

    description: str | None

    created_by_admin_id: int | None
    confirmed_by_admin_id: int | None

    gateway_transaction_id: str | None

    confirmed_at: datetime | None
    paid_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class SAttachProviderPayment(BaseModel):
    """Привязка транзакции платёжного провайдера."""

    gateway_transaction_id: str
    gateway_payload: dict[Any, Any] | None

    source: PaymentSource = PaymentSource.GATEWAY


class STransactionIDFilter(BaseModel):
    """Фильтр по идентификатору транзакции."""

    id: UUID = Field(validation_alias=AliasChoices("id", "transaction_id"))


class STransactionPendingFilter(STransactionIDFilter):
    """Фильтр по ID транзакции, дополнительно требующий статус ``PENDING``.

    Используется в UPDATE-запросах подтверждения/отмены платежа, чтобы
    проверка статуса и сама запись выполнялись атомарно на уровне БД
    (``WHERE id = ... AND status = 'PENDING'``), а не отдельным
    check-then-act в Python — иначе два параллельных вебхука могут оба
    пройти проверку статуса до того, как первый из них закоммитится.
    """

    status: PaymentStatus = PaymentStatus.PENDING


class SGatewayTransactionFilter(BaseModel):
    """Фильтр по ID транзакции платёжного шлюза."""

    gateway_transaction_id: str


class SUserPendingTransactionsFilter(BaseModel):
    """Фильтр незавершённых транзакций конкретного пользователя.

    Attributes
        user_id: Идентификатор пользователя.
        status: Статус транзакции (по умолчанию PENDING).

    """

    user_id: int
    status: PaymentStatus = PaymentStatus.PENDING


class SAdminConfirmPayment(STransactionIDFilter):
    """Схема подтверждения платежа администратором.

    Attributes
        admin_id: ID администратора, подтверждающего платёж.

    """

    admin_id: int


class SPaidAt(BaseModel):
    """Схема установки даты оплаты."""

    paid_at: datetime = Field(default_factory=datetime.now)


class SPaymentStatusCancel(BaseModel):
    """Схема отмены платежа."""

    status: PaymentStatus = PaymentStatus.CANCELED


class SPaymentStatusUpdate(BaseModel):
    """Обновление статуса платежа.

    Attributes
        status: Новый статус платежа.
        confirmed_by_admin_id: ID администратора, подтвердившего платеж.
        confirmed_at: Дата подтверждения.
        paid_at: Дата оплаты.
        source: Источник изменения статуса.

    """

    status: PaymentStatus
    confirmed_by_admin_id: int | None = None
    confirmed_at: datetime
    paid_at: datetime
    source: PaymentSource
    model_config = ConfigDict(
        from_attributes=True,
        extra="forbid",
    )


class SConfirmPaymentResponse(BaseModel):
    """Результат подтверждения платежа.

    Attributes
        transaction_res: Обновлённая транзакция.
        subscription_res: Обновлённые данные пользователя.
        referral_res: Результат начисления реферального бонуса.

    """

    transaction_res: SPaymentTransactionResponse
    subscription_res: SUserOut
    referral_res: GrantReferralBonusResponse


class SYearIncome(BaseModel):
    """Суммарный доход за год.

    Attributes
        year_income:
            Общая сумма дохода за год.

    """

    year_income: int
