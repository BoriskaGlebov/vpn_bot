from dataclasses import asdict
from decimal import Decimal
from uuid import UUID

from bot.payment.adapter import PaymentAPIAdapter
from bot.payment.schemas import (
    SPaymentTransactionResponse,
    SConfirmPaymentResponse,
    SCreatePayment,
)
from bot.payment.providers.payment_client import BasePaymentProvider
from bot.payment.dto import CreatePaymentDTO, CreatedPaymentDTO
from bot.subscription.enums import ToggleSubscriptionMode


#TODO  Новый класс не протестирован, нужно логирование, тесты, документация, типы данных
class PaymentService:
    def __init__(self,adapter:PaymentAPIAdapter,provider:BasePaymentProvider):
        self.adapter=adapter
        self.provider=provider

    async def create_transaction(self,amount:int,
                                 subscription_months:int,
                                 is_premium:bool,
                                 is_founder:bool)-> SCreatePayment:
        api_res=await self.adapter.create_transaction(amount=amount,
                                                     subscription_months=subscription_months,
                                                     is_premium=is_premium,
                                                     is_founder=is_founder)
        if is_premium:
            sub_type=ToggleSubscriptionMode.PREMIUM
        elif is_founder:
            sub_type=ToggleSubscriptionMode.FOUNDER
        else:
            sub_type = ToggleSubscriptionMode.STANDARD
        payment_data=CreatePaymentDTO(amount=Decimal(amount),
                                      currency="RUB",
                                      order_id=str(api_res.id),
                                      description=f"Оплата {sub_type.value} подписки на {subscription_months}мес.",
                                      )

        prov_res:CreatedPaymentDTO=await self.provider.create_payment(data=payment_data)
        tx_final=await self.adapter.attach_provider_payment(transaction_id=api_res.id,
                                                   gateway_transaction_id=payment_data.order_id,
                                                   gateway_payload=asdict(prov_res))

        return SCreatePayment(payment_url=prov_res.payment_url,**tx_final.model_dump(),)

    async def cancel_transaction(self,
                                 transaction_id: UUID)-> SPaymentTransactionResponse:
        tx_res=await self.adapter.cancel_transaction(transaction_id=transaction_id)
        return tx_res

    async def confirm_transaction(self,
                                 transaction_id: UUID)-> SConfirmPaymentResponse:
        tx_res=await self.adapter.confirm_transaction(transaction_id=transaction_id)
        return tx_res

    async def mark_payment_started(self,transaction_id: UUID):
        tx_res=await self.adapter.mark_payment_started(transaction_id=transaction_id)

        return tx_res

