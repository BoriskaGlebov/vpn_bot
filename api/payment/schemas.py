from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from api.payment.model import PaymentSource, PaymentStatus
from api.referrals.schemas import GrantReferralBonusResponse
from api.users.schemas import SUserOut

# TODO Слишком много схем?


class SCreateManualPaymentTransaction(BaseModel):
    """Схема создания ручной платежной транзакции.

    Attributes
        amount:
            Сумма платежа в минимальных единицах валюты.

        currency:
            Код валюты по ISO 4217.

        subscription_months:
            Количество месяцев подписки.

        is_premium:
            Флаг премиум-подписки.

        is_founder:
            Флаг founder-статуса.

        description:
            Дополнительное описание платежа.

    """

    amount: int = Field(gt=0)
    currency: str = "RUB"

    subscription_months: int = Field(gt=0)
    is_premium: bool = False
    is_founder: bool = False

    description: str | None = None


class SCreateTransaction(SCreateManualPaymentTransaction):
    """Схема создания платежной транзакции.

    Используется для создания уже оплаченной транзакции
    с привязкой к пользователю.

    Attributes
        user_id:
            ID пользователя.



    """

    user_id: int

    model_config = ConfigDict(from_attributes=True)


class SAttachProviderPayment(BaseModel):
    """Привязка транзакции платёжного провайдера."""

    gateway_transaction_id: str
    gateway_payload: dict[Any, Any] | None

    source: PaymentSource = PaymentSource.GATEWAY


class SPaymentTransactionResponse(BaseModel):
    """Схема ответа платежной транзакции.

    Attributes
        id:
            UUID транзакции.

        user_id:
            ID пользователя.

        tg_id:
            Telegram ID пользователя.

        amount:
            Сумма платежа.

        currency:
            Код валюты.

        status:
            Статус платежа.

        source:
            Источник создания платежа.

        subscription_months:
            Количество месяцев подписки.

        is_premium:
            Флаг премиум-подписки.

        is_founder:
            Флаг founder-статуса.

        description:
            Описание платежа.

        created_by_admin_id:
            ID администратора, создавшего транзакцию.

        confirmed_by_admin_id:
            ID администратора, подтвердившего платеж.

        gateway_transaction_id:
            ID транзакции в платежном шлюзе.

        confirmed_at:
            Дата подтверждения платежа.

        paid_at:
            Дата успешной оплаты.

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


class SGatewayTransactionFilter(BaseModel):
    gateway_transaction_id: str


class SConfirmPaymentResponse(BaseModel):
    """Результат подтверждения платежа.

    Attributes
        transaction_res:
            Обновленная платежная транзакция.

        subscription_res:
            Обновленные данные пользователя после выдачи подписки.

        referral_res:
            Результат начисления реферального бонуса.

    """

    transaction_res: SPaymentTransactionResponse
    subscription_res: SUserOut
    referral_res: GrantReferralBonusResponse


class SConfirmPaymentIn(BaseModel):
    """Схема подтверждения платежа.

    Attributes
        transaction_id:
            UUID платежной транзакции.

    """

    transaction_id: UUID


class SConfirmInID(BaseModel):
    """Схема идентификатора транзакции.

    Используется для метода DAO find_one_by_id

    Attributes
        id:
            UUID транзакции.

    """

    id: UUID


# TODO Добавил поле
class SConfirmPaymentConfirmUpdate(BaseModel):
    """Схема обновления подтверждения платежа.

    Attributes
        status:
            Новый статус платежа.

        confirmed_by_admin_id:
            ID администратора, подтвердившего платеж.

        confirmed_at:
            Дата и время подтверждения.

    """

    status: PaymentStatus
    confirmed_by_admin_id: int | None = None
    confirmed_at: datetime
    paid_at: datetime = (datetime.now(),)
    source: PaymentSource = PaymentSource.MANUAL
    model_config = ConfigDict(from_attributes=True)


class SCancelPaymentUpdate(BaseModel):
    status: PaymentStatus


class SPaidAt(BaseModel):
    paid_at: datetime = datetime.now()


class SConfirmPayment(SConfirmPaymentIn):
    """Схема подтверждения платежа администратором.

    Attributes
        transaction_id:
            UUID платежной транзакции.

        admin_id:
            ID администратора.

    """

    admin_id: int


class SCancelPaymentIn(BaseModel):
    """Схема отмены платежа.

    Attributes
        transaction_id:
            UUID платежной транзакции.

    """

    transaction_id: UUID


class SCancelInID(BaseModel):
    """Схема идентификатора отменяемой транзакции.

    Используется для метода DAO find_one_by_id.

    Attributes
        id:
            UUID транзакции.

    """

    id: UUID


class SCancelPayment(BaseModel):
    """Схема отмены платежа администратором.

    Attributes
        transaction_id:
            UUID платежной транзакции.


    """

    transaction_id: UUID


class SYearIncome(BaseModel):
    """Суммарный доход за год.

    Attributes
        year_income:
            Общая сумма дохода за год.

    """

    year_income: int
