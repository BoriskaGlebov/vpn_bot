from enum import StrEnum


class SubscriptionAction(StrEnum):
    """Действия, связанные с выбором подписки.

    Attributes
        SELECT: Пользователь выбирает платный период подписки.
        TRIAL: Пользователь выбирает пробный период. Отдельное действие, а
            не особое значение `months` — ранее признаком пробного периода
            было совпадение `months` с числом его длительности в днях
            (`TRIAL_PERIOD_SENTINEL`), из-за чего платный тариф на столько
            же месяцев было невозможно завести, а смена длительности триала
            меняла и признак его выбора. Длительность теперь
            берётся из `settings.core.trial_period_days`.
        PAY_CARD: Пользователь выбрал оплату картой (автоматически, через платёжный шлюз).
        PAY_TRANSFER: Пользователь выбрал оплату переводом (вручную, с проверкой администратором).
        PAID: Пользователь подтвердил перевод ("Я оплатил") — ждём проверки администратором.
        ENTER_PROMO: Пользователь хочет ввести промокод на скидку.
        CANCEL: Отмена

    """

    SELECT = "select"
    TRIAL = "trial"
    PAY_CARD = "pay_card"
    PAY_TRANSFER = "pay_transfer"
    PAID = "paid"
    ENTER_PROMO = "enter_promo"
    CANCEL = "cancel"


class AdminPaymentAction(StrEnum):
    """Действия администратора при обработке платежей.

    Attributes
        CONFIRM: Подтверждение оплаты администратором.
        DECLINE: Отклонение оплаты администратором.

    """

    CONFIRM = "confirm"
    DECLINE = "decline"


class MySubscriptionAction(StrEnum):
    """Действия под карточкой "Моя подписка" главного меню.

    Attributes
        RENEW: Оформить новую или продлить текущую подписку.

    """

    RENEW = "renew"
