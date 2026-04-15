from api.vpn.services import VPNService


def get_vpn_service() -> VPNService:
    """Depends для VPNService."""
    return VPNService()
