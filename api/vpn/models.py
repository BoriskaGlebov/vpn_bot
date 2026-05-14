from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, int_pk

if TYPE_CHECKING:
    from api.users.models import User
# TODO Мне нужна новая модель для хранения конфиг файлов 3xui


class VPNConfigStatus(str, Enum):
    """Статус жизненного цикла конфигурации VPN.

    Attributes
        ACTIVE: Конфигурация активна и используется.
        PENDING_DELETE: Конфигурация помечена для удаления.
        DELETED: Конфигурация удалена.

    """

    ACTIVE = "active"
    PENDING_DELETE = "pending_delete"
    DELETED = "deleted"


class VPNConfig(Base):
    """Модель VPN-конфигурации (WireGuard, AmneziaWG).

    Attributes
        id (int): Уникальный идентификатор записи.
        user_id (int): Внешний ключ на пользователя.
        file_name (str): Название файла конфига (например, `amnezia_wg_abc123.conf`).
        pub_key (str): Публичный ключ WireGuard пользователя.
        created_at (datetime): Дата и время создания конфига.
        user (User): Пользователь, которому принадлежит конфиг.

    """

    id: Mapped[int_pk]
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    pub_key: Mapped[str] = mapped_column(String(255), unique=False, nullable=False)
    status: Mapped[VPNConfigStatus] = mapped_column(
        SQLEnum(VPNConfigStatus, name="vpn_config_status"),
        default=VPNConfigStatus.ACTIVE,
        nullable=False,
    )
    user: Mapped["User"] = relationship(
        "User", back_populates="vpn_configs", lazy="selectin"
    )

    def __str__(self) -> str:
        """Строковое представление для отладки и логов."""
        return f"VPNConfig({self.file_name}, user_id={self.user_id})"
