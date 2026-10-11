"""Права на удаление в SQLAdmin-представлениях и экранирование badge() (#246)."""

from api.admin.badges import badge
from api.payment.admin import PaymentTransactionAdmin
from api.users.admin import UserAdmin
from api.vpn.admin import VPNConfigAdmin


def test_user_admin_delete_disabled():
    """Удаление User из админки запрещено — каскад снёс бы vpn_configs
    вместе с pub_key/config_ids, по которым можно отозвать доступ.
    """
    assert UserAdmin.can_delete is False


def test_vpn_config_admin_delete_disabled():
    """Удаление VPNConfig из админки запрещено — SQLAdmin не вызывает
    VPNService.delete_user_config и не отзывает доступ на ноде, только
    удаляет запись из БД.
    """
    assert VPNConfigAdmin.can_delete is False


def test_payment_transaction_admin_delete_disabled():
    """Удаление платёжной транзакции запрещено — потеря финансовой истории."""
    assert PaymentTransactionAdmin.can_delete is False


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
