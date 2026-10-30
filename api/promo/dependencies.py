from api.promo.services import PromoService


def get_promo_service() -> PromoService:
    """Возвращает экземпляр PromoService."""
    return PromoService()
