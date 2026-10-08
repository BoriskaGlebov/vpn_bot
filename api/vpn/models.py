from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import JSON
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.core.database import Base, int_pk

if TYPE_CHECKING:
    from api.users.models import User


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


# node_name и protocol — не SQLEnum (postgres native enum), а обычные строки.
# node_name валидируется на уровне кода по settings_bot.vpn.nodes, чтобы не
# дублировать список серверов в БД. protocol хранит конкретный протокол/версию
# (значения `VPNProtocol`: wg_v2, wg_v3, vless_reality_tcp, ...) — список будет
# расти, а native enum потребовал бы ALTER TYPE на каждое новое значение.
class VPNConfig(Base):
    """Модель VPN-конфигурации (WireGuard/AmneziaWG, XRay/3x-ui).

    Attributes
        id (int): Уникальный идентификатор записи.
        user_id (int): Внешний ключ на пользователя.
        file_name (str): Название файла конфига (например, `amnezia_wg_abc123.conf`).
        pub_key (str): Публичный ключ WireGuard пользователя.
        node_name (str | None): Имя ноды/локации (ключ в settings_bot.vpn.nodes,
            например "main", "sof", "fi", "waw"). Позволяет обращаться сразу
            к нужному серверу вместо перебора всех локаций.
        backend (str | None): Каким адаптером обслуживается конфиг, значения
            из `VPNBackend`.
        protocol (str | None): Конкретный протокол/версия внутри бэкенда,
            значения из `VPNProtocol`.
        config_ids (list | None): Для XRay — список uuid клиентов на панели
            (по одному на каждый inbound этой подписки), нужен для точечного
            удаления/продления без перебора.
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
    node_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    backend: Mapped[str | None] = mapped_column(String(20), nullable=True)
    protocol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    user: Mapped["User"] = relationship(
        "User", back_populates="vpn_configs", lazy="selectin"
    )

    def __str__(self) -> str:
        """Строковое представление для отладки и логов."""
        return f"VPNConfig({self.file_name}, user_id={self.user_id})"
