from api.admin.services import AdminService


def get_admin_service() -> AdminService:
    """Depends для AdminService."""
    return AdminService()
