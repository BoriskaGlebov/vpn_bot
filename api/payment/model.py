# class PaymentStatus(str, Enum):
#     PENDING = "pending"
#     PAID = "paid"
#     FAILED = "failed"
#     EXPIRED = "expired"
#
# class Payment(Base):
#     __tablename__ = "payments"
#
#     id: Mapped[UUID]
#     user_id: Mapped[int]
#
#     provider: Mapped[str]
#     provider_payment_id: Mapped[str]
#
#     amount: Mapped[Decimal]
#     currency: Mapped[str]
#
#     status: Mapped[PaymentStatus]
#
#     tariff_code: Mapped[str]
#
#     created_at: Mapped[datetime]
#     paid_at: Mapped[datetime | None]
#
#     metadata: Mapped[dict | None]

#
# Что должно быть в payment metadata
#
# Очень помогает:
#
# {
#     "telegram_id": 123456,
#     "tariff": "1m",
#     "duration_days": 30
# }
