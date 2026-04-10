from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from api.referrals.dao import ReferralDAO
from api.referrals.models import Referral


@pytest.mark.asyncio
async def test_add_referral_success(mock_session):
    inviter_id = 1
    invited_id = 2

    # Выполняем метод
    referral = await ReferralDAO.add_referral(
        session=mock_session,
        inviter_id=inviter_id,
        invited_id=invited_id,
    )

    # Проверяем, что возвращается объект Referral
    assert isinstance(referral, Referral)
    assert referral.inviter_id == inviter_id
    assert referral.invited_id == invited_id
    assert referral.bonus_given is False
    assert referral.bonus_given_at is None

    # Проверяем вызовы методов сессии
    mock_session.add.assert_called_once_with(referral)
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_add_referral_logs_info(mock_session):
    inviter_id = 10
    invited_id = 20

    with patch("api.referrals.dao.logger") as mock_logger:
        await ReferralDAO.add_referral(
            session=mock_session,
            inviter_id=inviter_id,
            invited_id=invited_id,
        )

        mock_logger.info.assert_called_once()
        log_message = mock_logger.info.call_args[0][0]
        assert f"inviter={inviter_id}" in log_message
        assert f"invited={invited_id}" in log_message


@pytest.mark.asyncio
async def test_add_referral_sqlalchemy_error(mock_session):
    inviter_id = 1
    invited_id = 2

    # Настраиваем flush так, чтобы он выбрасывал исключение
    mock_session.flush.side_effect = SQLAlchemyError("DB error")

    with patch("api.referrals.dao.logger") as mock_logger:
        with pytest.raises(SQLAlchemyError):
            await ReferralDAO.add_referral(
                session=mock_session,
                inviter_id=inviter_id,
                invited_id=invited_id,
            )

        # Проверяем, что add был вызван до возникновения ошибки
        assert mock_session.add.called

        # Проверяем логирование ошибки
        mock_logger.error.assert_called_once()
        assert "Ошибка при добавлении записи" in mock_logger.error.call_args[0][0]
