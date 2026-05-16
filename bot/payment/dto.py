# import datetime
# from dataclasses import dataclass
# from decimal import Decimal
# from enum import Enum
#
#
# @dataclass(slots=True)
# class CreatePaymentDTO:
#     amount: Decimal
#     currency: str
#     order_id: str
#     description: str
#     success_url: str
#     failed_url: str
#     payload: str | None = None
#
# class PaymentStatus(str, Enum):
#     PENDING = "pending"
#     PAID = "paid"
#     FAILED = "failed"
#
# @dataclass(slots=True)
# class CreatedPaymentDTO:
#     provider_payment_id: str
#     payment_url: str
#     status:PaymentStatus
#     expires_at: str | None = None
#     rate: float | None = None
#
#
#
#
# @dataclass(slots=True)
# class PaymentWebhookDTO:
#     provider_payment_id: str
#     status: PaymentStatus
#     raw_data: dict
#
#     payload: str | None = None
