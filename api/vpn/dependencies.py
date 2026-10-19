from api.vpn.services import VPNService


def get_vpn_service() -> VPNService:
    """Возвращает экземпляр VPNService."""
    return VPNService()
