from api.payment.services import PaymentService


def get_payment_service() -> PaymentService:
    """Depends для PaymentService."""
    return PaymentService()
