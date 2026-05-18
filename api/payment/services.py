from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    PaymentAlreadyProcessedError,
    PaymentTransactionNotFoundError,
)
from api.payment.dao import PaymentTransactionDAO
from api.payment.model import PaymentStatus
from api.payment.schemas import (
    SCancelInID,
    SCancelPayment,
    SConfirmInID,
    SConfirmPayment,
    SConfirmPaymentConfirmUpdate,
    SCreateManualPaymentTransaction,
    SCreateTransaction,
    SPaymentTransactionResponse,
    SYearIncome,
)
from api.users.models import User


class PaymentService:
    """Сервис для работы с платежными транзакциями.

    Отвечает за:
        - создание транзакций;
        - подтверждение платежей;
        - отмену платежей;
        - получение финансовой статистики.
    """

    async def create_transaction(
        self,
        session: AsyncSession,
        transaction: SCreateManualPaymentTransaction,
        user_auth: User,
    ) -> SPaymentTransactionResponse:
        """Создает новую платежную транзакцию.

        Args:
            session:
                Асинхронная SQLAlchemy-сессия.

            transaction:
                Данные создаваемой транзакции.

            user_auth:
                Авторизованный пользователь.

        Returns
            Данные созданной платежной транзакции.

        """
        logger.info(
            f"[SERVICE] Создание платежной транзакции "
            f"для пользователя ID={user_auth.id}"
        )
        payment_schema = SCreateTransaction(
            user_id=user_auth.id,
            paid_at=datetime.now(),
            **transaction.model_dump(exclude_unset=True),
        )
        res = await PaymentTransactionDAO.add(
            session=session,
            values=payment_schema,
        )
        logger.success(
            f"[SERVICE] Платежная транзакция успешно создана. Transaction ID={res.id}"
        )

        return SPaymentTransactionResponse.model_validate(res)

    async def confirm_transaction(
        self, data: SConfirmPayment, session: AsyncSession
    ) -> SPaymentTransactionResponse:
        """Подтверждает платежную транзакцию.

        Изменяет статус транзакции на ``PAID``.

        Args:
            data:
                Данные подтверждения платежа.

            session:
                Асинхронная SQLAlchemy-сессия.

        Returns
            Обновленная платежная транзакция.

        Raises
            PaymentTransactionNotFoundError:
                Если транзакция не найдена.

            PaymentAlreadyProcessedError:
                Если транзакция уже обработана.

        """
        logger.info(
            f"[SERVICE] Подтверждение платежной транзакции ID={data.transaction_id}"
        )
        tx = await PaymentTransactionDAO.find_one_or_none_by_id(
            session=session, data_id=data.transaction_id
        )

        if not tx:
            logger.warning(
                f"[SERVICE] Транзакция не найдена. Transaction ID={data.transaction_id}"
            )
            raise PaymentTransactionNotFoundError(
                transaction_id=str(data.transaction_id)
            )

        if tx.status != PaymentStatus.PENDING:
            logger.warning(
                f"[SERVICE] Попытка повторной обработки транзакции. "
                f"Transaction ID={data.transaction_id}. "
                f"Текущий статус={tx.status.value}"
            )
            raise PaymentAlreadyProcessedError(
                transaction_id=str(data.transaction_id), status=tx.status
            )

        await PaymentTransactionDAO.update(
            session=session,
            filters=SConfirmInID(id=data.transaction_id),
            values=SConfirmPaymentConfirmUpdate(
                status=PaymentStatus.PAID,
                confirmed_by_admin_id=data.admin_id,
                confirmed_at=datetime.now(),
            ),
        )
        await session.refresh(tx)
        logger.success(
            f"[SERVICE] Транзакция подтверждена. Transaction ID={data.transaction_id}"
        )
        return SPaymentTransactionResponse.model_validate(tx)

    async def cancel_transaction(
        self,
        session: AsyncSession,
        data: SCancelPayment,
    ) -> SPaymentTransactionResponse:
        """Отменяет платежную транзакцию.

        Изменяет статус транзакции на ``CANCELED``.

        Args:
            session:
                Асинхронная SQLAlchemy-сессия.

            data:
                Данные отмены платежа.

        Returns
            Обновленная платежная транзакция.

        Raises
            PaymentTransactionNotFoundError:
                Если транзакция не найдена.

            PaymentAlreadyProcessedError:
                Если транзакция уже обработана.

        """
        logger.info(f"[SERVICE] Отмена платежной транзакции ID={data.transaction_id}")
        tx = await PaymentTransactionDAO.find_one_or_none_by_id(
            session=session,
            data_id=data.transaction_id,
        )

        if not tx:
            logger.warning(
                f"[SERVICE] Транзакция для отмены не найдена. "
                f"Transaction ID={data.transaction_id}"
            )
            raise PaymentTransactionNotFoundError(
                transaction_id=str(data.transaction_id),
            )

        if tx.status != PaymentStatus.PENDING:
            logger.warning(
                f"[SERVICE] Попытка отмены уже обработанной транзакции. "
                f"Transaction ID={data.transaction_id}. "
                f"Текущий статус={tx.status.value}"
            )

            raise PaymentAlreadyProcessedError(
                transaction_id=str(data.transaction_id),
                status=tx.status,
            )

        await PaymentTransactionDAO.update(
            session=session,
            filters=SCancelInID(id=data.transaction_id),
            values=SConfirmPaymentConfirmUpdate(
                status=PaymentStatus.CANCELED,
                confirmed_by_admin_id=data.admin_id,
                confirmed_at=datetime.now(),
            ),
        )
        await session.refresh(tx)
        logger.success(
            f"[SERVICE] Транзакция отменена. Transaction ID={data.transaction_id}"
        )
        return SPaymentTransactionResponse.model_validate(tx)

    async def get_year_income(
        self,
        session: AsyncSession,
        year: int | None = None,
    ) -> SYearIncome:
        """Возвращает суммарный доход за год.

        Args:
            session:
                Асинхронная SQLAlchemy-сессия.

            year:
                Год для расчета дохода.
                Если не указан — используется текущий год.

        Returns
            Суммарный доход за указанный год.

        """
        logger.info(
            f"[SERVICE] Получение годового дохода. "
            f"Год={year or datetime.now(tz=UTC).year}"
        )
        res = await PaymentTransactionDAO.get_year_income(
            session=session,
            year=year,
        )
        logger.success(f"[SERVICE] Годовой доход успешно получен. Сумма={res}")
        return SYearIncome(year_income=res)
