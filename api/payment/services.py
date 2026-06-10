from datetime import UTC, datetime
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.app_error.base_error import (
    PaymentAlreadyProcessedError,
    PaymentTransactionNotFoundError,
    ReferralBonusAlreadyGivenError,
)
from api.payment.dao import PaymentTransactionDAO
from api.payment.model import PaymentSource, PaymentStatus, PaymentTransaction
from api.payment.schemas import (
    SAdminConfirmPayment,
    SAttachProviderPayment,
    SConfirmPaymentResponse,
    SCreateManualPaymentTransaction,
    SCreateTransaction,
    SGatewayTransactionFilter,
    SPaidAt,
    SPaymentStatusCancel,
    SPaymentStatusUpdate,
    SPaymentTransactionResponse,
    STransactionIDFilter,
    SYearIncome,
)
from api.referrals.schemas import GrantReferralBonusResponse
from api.referrals.services import ReferralService
from api.subscription.services import SubscriptionService
from api.users.models import User


class PaymentService:
    """Сервис работы с платежными транзакциями.

    Предоставляет бизнес-операции для управления платежными
    транзакциями и post-payment процессами.

    Сервис отвечает за:
        - создание платежных транзакций;
        - привязку транзакций платёжных провайдеров;
        - подтверждение и отмену платежей;
        - контроль допустимых статусов транзакций;
        - активацию подписок после успешной оплаты;
        - начисление реферальных бонусов;
        - получение финансовой статистики.

    Особенности реализации:
        - инкапсулирует бизнес-правила платежной системы;
        - выполняет проверки состояния транзакций;
        - координирует post-payment flow;
        - делегирует CRUD-операции DAO-слою;
        - обеспечивает консистентность состояния платежей.

    Attributes
        sub_service:
            Сервис управления подписками.

        ref_service:
            Сервис реферальной системы.

    """

    def __init__(
        self, sub_service: SubscriptionService, ref_service: ReferralService
    ) -> None:
        """Инициализирует сервис платежей.

        Args:
            sub_service:
                Сервис управления подписками.

            ref_service:
                Сервис работы с реферальной системой.

        """
        self.sub_service = sub_service
        self.ref_service = ref_service

    async def _get_transaction_or_raise(
        self,
        session: AsyncSession,
        transaction_id: UUID,
    ) -> PaymentTransaction:
        """Получает платежную транзакцию по ID или вызывает исключение.

        Выполняет запрос к базе данных для получения платежной транзакции.
        Если транзакция не найдена — выбрасывается исключение
        `PaymentTransactionNotFoundError`.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            transaction_id: UUID идентификатор транзакции.

        Returns
            PaymentTransaction: Найденная транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не существует.

        """
        tx = await PaymentTransactionDAO.find_one_or_none_by_id(
            session=session,
            data_id=transaction_id,
        )
        if not tx:
            raise PaymentTransactionNotFoundError(
                transaction_id=str(transaction_id),
            )
        return tx

    def _ensure_pending(self, tx: PaymentTransaction) -> None:
        """Проверяет, что транзакция находится в статусе PENDING.

        Используется для защиты от повторной обработки уже завершённых
        или отменённых платежей.

        Args:
            tx: Платежная транзакция.

        Raises
            PaymentAlreadyProcessedError: Если статус транзакции не PENDING.

        """
        if tx.status != PaymentStatus.PENDING:
            logger.warning(
                "[SERVICE] Попытка повторной обработки транзакции | "
                "transaction_id={} | status={}",
                tx.id,
                tx.status,
            )
            raise PaymentAlreadyProcessedError(
                transaction_id=str(tx.id),
                payment_status=tx.status,
            )

    async def create_transaction(
        self,
        session: AsyncSession,
        transaction: SCreateManualPaymentTransaction,
        user_auth: User,
    ) -> SPaymentTransactionResponse:
        """Создаёт новую платежную транзакцию.

        Создаёт запись платежной транзакции в системе для указанного пользователя.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            transaction: Данные создаваемой транзакции.
            user_auth: Авторизованный пользователь.

        Returns
            SPaymentTransactionResponse: Созданная платежная транзакция.

        """
        logger.info(
            f"[SERVICE] Создание платежной транзакции "
            f"для пользователя ID={user_auth.id}"
        )
        payment_schema = SCreateTransaction(
            user_id=user_auth.id,
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

    async def get_by_gateway_id(
        self,
        session: AsyncSession,
        gateway_transaction_id: str,
    ) -> SPaymentTransactionResponse:
        """Возвращает транзакцию по ID платёжного провайдера.

        Выполняет поиск внутренней транзакции, связанной с внешним
        идентификатором платёжного шлюза.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            gateway_transaction_id: ID транзакции во внешнем платёжном сервисе.

        Returns
            SPaymentTransactionResponse: Найденная транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.

        """
        logger.info(
            "[SERVICE] gateway_transaction_id={}",
            gateway_transaction_id,
        )
        tx = await PaymentTransactionDAO.find_one_or_none(
            session=session,
            filters=SGatewayTransactionFilter(
                gateway_transaction_id=gateway_transaction_id
            ),
        )

        if not tx:
            logger.warning(
                "[SERVICE] Не найдена транзакция gateway_transaction_id={}",
                gateway_transaction_id,
            )
            raise PaymentTransactionNotFoundError(
                transaction_id=None, gateway_transaction_id=gateway_transaction_id
            )
        logger.info(
            "[SERVICE] Платежная транзакция найдена gateway_transaction_id={} transaction_id={}",
            gateway_transaction_id,
            tx.id,
        )

        return SPaymentTransactionResponse.model_validate(tx)
    async def attach_provider_payment(
        self,
        session: AsyncSession,
        transaction_id: UUID,
        gateway_info: SAttachProviderPayment,
    ) -> SPaymentTransactionResponse:
        """Привязывает платёж провайдера к внутренней транзакции.

        Сохраняет идентификатор транзакции платёжного шлюза и связанные
        данные провайдера для дальнейшей обработки webhook-событий и
        сопоставления с внутренними транзакциями системы.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            transaction_id: UUID внутренней транзакции.
            gateway_info: Данные от внешнего платёжного провайдера.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.

        """
        logger.info(
            "[SERVICE] Привязка provider transaction internal_id={} gateway_transaction_id={}",
            transaction_id,
            gateway_info.gateway_transaction_id,
        )

        num_row = await PaymentTransactionDAO.update(
            session=session,
            filters=STransactionIDFilter(id=transaction_id),
            values=gateway_info,
        )

        if not num_row:
            logger.warning(
                f"[SERVICE] Транзакция не найдена при привязке provider payment "
                f"| internal_id={transaction_id} "
                f"gateway_transaction_id={gateway_info.gateway_transaction_id}"
            )

            raise PaymentTransactionNotFoundError(
                transaction_id=str(transaction_id),
                gateway_transaction_id=gateway_info.gateway_transaction_id,
            )
        transaction = await self._get_transaction_or_raise(
            session=session, transaction_id=transaction_id
        )
        logger.success(
            f"[SERVICE] Provider transaction успешно привязан "
            f"internal_id={transaction_id} gateway_transaction_id={gateway_info.gateway_transaction_id}"
        )

        return SPaymentTransactionResponse.model_validate(transaction)

    async def mark_payment_started(
        self,
        session: AsyncSession,
        transaction_id: UUID,
    ) -> SPaymentTransactionResponse:
        """Помечает начало обработки платежа.

        Обновляет дату начала обработки платежа (paid_at или аналогичное поле),
        фиксируя момент старта платежного процесса.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            transaction_id: UUID внутренней транзакции.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.

        """
        logger.info(
            f"[SERVICE] Начало обработки платежа | transaction_id={transaction_id}"
        )
        upd_transaction = await PaymentTransactionDAO.update(
            session=session,
            filters=STransactionIDFilter(id=transaction_id),
            values=SPaidAt(paid_at=datetime.now()),
        )

        if not upd_transaction:
            logger.warning(
                f"[SERVICE] Транзакция не найдена при mark_payment_started "
                f"| transaction_id={transaction_id}"
            )

            raise PaymentTransactionNotFoundError(
                transaction_id=str(transaction_id),
            )
        transaction = await self._get_transaction_or_raise(
            session=session, transaction_id=transaction_id
        )
        logger.success(
            f"[SERVICE] Начало обработки платежа зафиксировано "
            f"| transaction_id={transaction_id}"
        )
        return SPaymentTransactionResponse.model_validate(transaction)
    async def admin_confirm_transaction(
        self, data: SAdminConfirmPayment, session: AsyncSession
    ) -> SPaymentTransactionResponse:
        """Подтверждает платежную транзакцию администратором.

        Переводит статус транзакции в ``PAID`` и фиксирует данные администратора,
        подтвердившего платёж.

        Args:
            data: Данные подтверждения платежа.
            session: Асинхронная SQLAlchemy-сессия.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.
            PaymentAlreadyProcessedError: Если транзакция уже обработана.

        """
        logger.info(f"[SERVICE] Подтверждение платежной транзакции ID={data.id}")
        tx = await self._get_transaction_or_raise(
            session=session, transaction_id=data.id
        )
        self._ensure_pending(tx=tx)

        await PaymentTransactionDAO.update(
            session=session,
            filters=STransactionIDFilter(id=data.id),
            values=SPaymentStatusUpdate(
                status=PaymentStatus.PAID,
                confirmed_by_admin_id=data.admin_id,
                confirmed_at=datetime.now(),
                paid_at=datetime.now(),
                source=PaymentSource.MANUAL,
            ),
        )
        await session.refresh(tx)
        logger.success(
            f"[SERVICE] Транзакция подтверждена администратором. Transaction ID={data.id}"
        )
        return SPaymentTransactionResponse.model_validate(tx)

    async def webhook_confirm_transaction(
        self, data: STransactionIDFilter, session: AsyncSession
    ) -> SPaymentTransactionResponse:
        """Подтверждает платежную транзакцию через webhook.

        Переводит статус транзакции в ``PAID`` на основании данных от
        платёжного провайдера.

        Args:
            data: Идентификатор транзакции.
            session: Асинхронная SQLAlchemy-сессия.

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.
            PaymentAlreadyProcessedError: Если транзакция уже обработана.

        """
        logger.info(f"[SERVICE] Подтверждение платежной транзакции ID={data.id}")
        tx = await self._get_transaction_or_raise(
            session=session, transaction_id=data.id
        )
        self._ensure_pending(tx=tx)

        await PaymentTransactionDAO.update(
            session=session,
            filters=STransactionIDFilter(id=data.id),
            values=SPaymentStatusUpdate(
                status=PaymentStatus.PAID,
                paid_at=datetime.now(),
                confirmed_at=datetime.now(),
                source=PaymentSource.GATEWAY,
            ),
        )
        await session.refresh(tx)
        logger.success(f"[SERVICE] Транзакция подтверждена. Transaction ID={data.id}")
        return SPaymentTransactionResponse.model_validate(tx)

    async def cancel_transaction(
        self,
        session: AsyncSession,
        data: STransactionIDFilter,
    ) -> SPaymentTransactionResponse:
        """Отменяет платежную транзакцию.

        Переводит статус транзакции в ``CANCELED``.

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            data: Данные отмены платежа (ID транзакции).

        Returns
            SPaymentTransactionResponse: Обновлённая транзакция.

        Raises
            PaymentTransactionNotFoundError: Если транзакция не найдена.
            PaymentAlreadyProcessedError: Если транзакция уже обработана.

        """
        logger.info(f"[SERVICE] Отмена платежной транзакции ID={data.id}")
        tx = await self._get_transaction_or_raise(
            session=session, transaction_id=data.id
        )
        self._ensure_pending(tx=tx)

        await PaymentTransactionDAO.update(
            session=session,
            filters=STransactionIDFilter(id=data.id),
            values=SPaymentStatusCancel(
                status=PaymentStatus.CANCELED,
            ),
        )
        await session.refresh(tx)
        logger.success(f"[SERVICE] Транзакция отменена. Transaction ID={data.id}")
        return SPaymentTransactionResponse.model_validate(tx)

    async def get_year_income(
        self,
        session: AsyncSession,
        year: int | None = None,
    ) -> SYearIncome:
        """Возвращает суммарный доход за указанный год.

        Если год не указан — используется текущий год (UTC).

        Args:
            session: Асинхронная SQLAlchemy-сессия.
            year: Год расчёта дохода.

        Returns
            SYearIncome: Суммарный доход за год.

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

    async def confirm_payment_flow(
        self,
        session: AsyncSession,
        data: STransactionIDFilter,
        payment_source: PaymentSource,
        admin_id: int | None = None,
    ) -> SConfirmPaymentResponse:
        """Подтверждает платежную транзакцию и запускает post-payment flow.

        Метод является orchestration-слоем процесса подтверждения оплаты.
        В зависимости от источника подтверждения выполняет:

            - подтверждение транзакции;
            - активацию подписки пользователя;
            - начисление реферального бонуса.

        Поддерживаются два режима подтверждения:

            - ``PaymentSource.GATEWAY`` — подтверждение через webhook
              внешнего платёжного провайдера;

            - ``PaymentSource.MANUAL`` — ручное подтверждение
              администратором.

        Args:
            session:
                Асинхронная SQLAlchemy-сессия.

            data:
                Данные подтверждаемой транзакции.

            payment_source:
                Источник подтверждения платежа.

            admin_id:
                ID администратора при ручном подтверждении платежа.
                Используется только для ``PaymentSource.MANUAL``.

        Returns
            SConfirmPaymentResponse:
                Результат подтверждения платежа, активации подписки
                и обработки реферального бонуса.

        Raises
            PaymentTransactionNotFoundError:
                Если транзакция не найдена.

            PaymentAlreadyProcessedError:
                Если транзакция уже была обработана.

            ValueError:
                Если передан некорректный источник подтверждения
                или отсутствует ``admin_id`` для ручного подтверждения.

        """
        if payment_source == PaymentSource.GATEWAY:
            tx = await self.webhook_confirm_transaction(session=session, data=data)
        elif payment_source.MANUAL and admin_id:
            tx = await self.admin_confirm_transaction(
                session=session,
                data=SAdminConfirmPayment(admin_id=admin_id, id=data.id),
            )
        else:
            raise ValueError("НЕВЕРНЫЙ payment_source или  пропущен admin_id")
        sub_res = await self.sub_service.activate_paid_subscription(
            session=session,
            user_id=tx.tg_id,
            months=tx.subscription_months,
            premium=tx.is_premium,
        )
        ref_mes = "Бонус по реферально программе начислен"
        try:
            ref_res, inviter = await self.ref_service.grant_referral_bonus(
                session=session,
                invited_user=sub_res,
            )
        except ReferralBonusAlreadyGivenError as e:
            ref_res = False
            inviter = None
            ref_mes = e.message
        return SConfirmPaymentResponse(
            transaction_res=tx,
            subscription_res=sub_res,
            referral_res=GrantReferralBonusResponse(
                success=ref_res,
                inviter_telegram_id=inviter,
                message=ref_mes,
            ),
        )
