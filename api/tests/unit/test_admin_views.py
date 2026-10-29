"""Права на удаление в SQLAdmin-представлениях и экранирование badge() (#246)."""

from api.admin.badges import badge
from api.payment.admin import PaymentTransactionAdmin
from api.users.admin import UserAdmin
from api.vpn.admin import VPNConfigAdmin


def test_user_admin_delete_enabled():
    """Удаление User из админки разрешено (#290) — on_model_delete отзывает
    доступ всех vpn_configs на нодах до того, как каскад их снесёт
    (см. test_user_admin.py).
    """
    assert UserAdmin.can_delete is True


def test_vpn_config_admin_delete_enabled():
    """Удаление VPNConfig из админки разрешено (#290) — on_model_delete
    отзывает доступ на ноде через BotChannelClient до удаления записи
    (см. test_vpn_config_admin.py).
    """
    assert VPNConfigAdmin.can_delete is True


def test_vpn_config_admin_create_and_edit_disabled():
    """Создание/редактирование VPNConfig через SQLAdmin запрещено (#272) —
    зеркально can_delete: SQLAdmin пишет модель напрямую в БД, минуя
    VPNConfigDAO.add_config (проверка лимита устройств) и выдачу доступа
    на ноде/панели. Созданная так запись — фантом без node_name/backend/
    protocol/config_ids, который занимает слот в лимите, но не удаляется
    (can_delete тоже False).
    """
    assert VPNConfigAdmin.can_create is False
    assert VPNConfigAdmin.can_edit is False


def test_payment_transaction_admin_delete_disabled():
    """Удаление платёжной транзакции запрещено — потеря финансовой истории."""
    assert PaymentTransactionAdmin.can_delete is False


def test_payment_transaction_admin_create_and_edit_disabled():
    """Создание/редактирование платёжной транзакции через SQLAdmin
    запрещено (#260) — обходило бы confirm_payment_flow, единственное
    место, где подтверждение сопровождается активацией подписки и
    продлением XRay-конфигов. Правка иначе рассогласовала бы транзакцию
    и подписку и не оставляла бы следа, кто её изменил.
    """
    assert PaymentTransactionAdmin.can_create is False
    assert PaymentTransactionAdmin.can_edit is False


def test_badge_escapes_html_in_text():
    """badge() экранирует text — иначе применение к полю, заполняемому
    пользователем, дало бы XSS в админке.
    """
    result = badge("<script>alert(1)</script>", "danger")

    assert "<script>" not in str(result)
    assert "&lt;script&gt;" in str(result)


def test_badge_renders_expected_markup_for_safe_text():
    """Обычный текст рендерится как и раньше, без лишнего экранирования разметки."""
    result = badge("Активен", "success")

    assert str(result) == '<span class="badge bg-success">Активен</span>'
