from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from bot.payment.enums import PaymentSource, PaymentStatus
from bot.referrals.schemas import GrantReferralBonusResponse
from bot.users.schemas import SUserOut


class SCreateManualPaymentTransactionIn(BaseModel):
    """DTO для создания платёжной транзакции вручную.

    Используется для формирования запроса на создание платежа через API.

    Attributes
        amount (int): Сумма платежа в минимальных единицах (например, копейки). Должна быть > 0.
        currency (Literal): Валюта платежа (например, RUB).
        subscription_months (int): Количество месяцев подписки. Должно быть > 0.
        is_premium (bool): Признак премиум-подписки.
        is_founder (bool): Признак пользователя-основателя.
        description (str | None): Описание платежа. Если не задано, генерируется автоматически.

    """

    amount: int = Field(gt=0)
    currency: Literal["RUB"]

    subscription_months: int = Field(gt=0)
    is_premium: bool = False
    is_founder: bool = False

    description: str | None = None

    @model_validator(mode="after")
    def build_description(self) -> "SCreateManualPaymentTransactionIn":
        """Формирует описание платежа, если оно не задано.

        Логика:
            - Определяет тип подписки (PREMIUM / STANDARD)
            - Формирует человекочитаемое описание с суммой и валютой

        Returns
            SCreateManualPaymentTransactionIn: обновлённый объект модели.

        """
        if not self.description:
            sub_type = "PREMIUM" if self.is_premium else "STANDARD"

            self.description = (
                f"Оплата {sub_type} подписки "
                f"на {self.subscription_months} мес. "
                f"({self.amount} {self.currency})"
            )

        return self


class SConfirmPaymentIn(BaseModel):
    """DTO для подтверждения платежной транзакции.

    Attributes
        transaction_id (UUID): Уникальный идентификатор транзакции.

    """

    transaction_id: UUID


class SCancelPaymentIn(BaseModel):
    """DTO для отмены платежной транзакции.

    Attributes
        transaction_id (UUID): Уникальный идентификатор транзакции.

    """

    transaction_id: UUID


# TODO Можно укоротить
class SPaymentTransactionResponse(BaseModel):
    """Ответ API с данными платежной транзакции.

    Attributes
        id (UUID): ID транзакции.
        user_id (int): ID пользователя.

        amount (int): Сумма платежа.
        currency (str): Валюта платежа.

        status (PaymentStatus): Текущий статус платежа.
        source (PaymentSource): Источник создания платежа.

        subscription_months (int): Длительность подписки в месяцах.
        is_premium (bool): Премиум-подписка.
        is_founder (bool): Пользователь-основатель.

        description (str | None): Описание транзакции.

        created_by_admin_id (int | None): ID админа, создавшего транзакцию.
        confirmed_by_admin_id (int | None): ID админа, подтвердившего транзакцию.

        gateway_transaction_id (str | None): ID транзакции в платёжном шлюзе.

        confirmed_at (datetime | None): Время подтверждения.
        paid_at (datetime | None): Время оплаты.

    """

    id: UUID

    user_id: int

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


class SConfirmPaymentResponse(BaseModel):
    """Ответ API после подтверждения платежа.

    Attributes
        transaction_res (SPaymentTransactionResponse): Обновлённая транзакция.
        subscription_res (SUserOut): Обновлённые данные пользователя/подписки.
        referral_res (GrantReferralBonusResponse): Результат начисления реферального бонуса.

    """

    transaction_res: SPaymentTransactionResponse
    subscription_res: SUserOut
    referral_res: GrantReferralBonusResponse
