"""Payment service for handling Telegram Stars payments."""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Payment,
    PaymentEvent,
    PaymentEventTypeEnum,
    PaymentMethodEnum,
    PaymentStatusEnum,
    Tariff,
    User,
)
from app.utils.logger import logger


class PaymentError(Exception):
    """Base exception for payment errors."""

    pass


class PaymentNotFoundError(PaymentError):
    """Payment not found error."""

    pass


class TariffNotFoundError(PaymentError):
    """Tariff not found error."""

    pass


class TariffNotAvailableError(PaymentError):
    """Tariff not available for purchase."""

    pass


class UserNotFoundError(PaymentError):
    """User not found error."""

    pass


class PaymentAlreadyCompletedError(PaymentError):
    """Payment already completed error."""

    pass


class PaymentAmountMismatchError(PaymentError):
    """Payment amount mismatch error."""

    pass


class PaymentInvalidStatusError(PaymentError):
    """Payment has invalid status for operation."""

    pass


async def log_payment_event(
    session: AsyncSession,
    payment_id: uuid.UUID,
    event_type: PaymentEventTypeEnum,
    status_before: str | None = None,
    status_after: str | None = None,
    details: dict | None = None,
    error_message: str | None = None,
) -> PaymentEvent:
    """Log a payment event for audit trail.
    
    Args:
        session: Database session
        payment_id: Payment UUID
        event_type: Type of event
        status_before: Status before event
        status_after: Status after event
        details: Additional details as JSON
        error_message: Error message if applicable
        
    Returns:
        Created PaymentEvent
    """
    event = PaymentEvent(
        payment_id=payment_id,
        event_type=event_type,
        status_before=status_before,
        status_after=status_after,
        details=details,
        error_message=error_message,
    )
    session.add(event)
    
    logger.info(
        f"Payment event logged: payment_id={payment_id}, type={event_type.value}, "
        f"status: {status_before} -> {status_after}"
    )
    
    return event


async def create_telegram_stars_payment(
    session: AsyncSession,
    user_id: int,
    tariff_id: uuid.UUID,
) -> tuple[Payment, Tariff]:
    """Create a new Telegram Stars payment.
    
    Args:
        session: Database session
        user_id: Telegram user ID
        tariff_id: Tariff UUID to purchase
        
    Returns:
        Tuple of (Payment, Tariff)
        
    Raises:
        UserNotFoundError: If user doesn't exist
        TariffNotFoundError: If tariff doesn't exist
        TariffNotAvailableError: If tariff is inactive or doesn't support Stars
    """
    # Verify user exists
    user_result = await session.execute(
        select(User).where(User.user_id == user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        logger.warning(f"User {user_id} not found for payment creation")
        raise UserNotFoundError(f"User {user_id} not found")
    
    # Get tariff
    tariff_result = await session.execute(
        select(Tariff).where(Tariff.tariff_id == tariff_id)
    )
    tariff = tariff_result.scalar_one_or_none()
    
    if not tariff:
        logger.warning(f"Tariff {tariff_id} not found for payment creation")
        raise TariffNotFoundError(f"Tariff {tariff_id} not found")
    
    if not tariff.is_active:
        logger.warning(f"Tariff {tariff_id} is not active")
        raise TariffNotAvailableError(f"Tariff {tariff_id} is not active")
    
    if not tariff.price_stars:
        logger.warning(f"Tariff {tariff_id} doesn't have Stars price")
        raise TariffNotAvailableError(f"Tariff {tariff_id} is not available for Telegram Stars")
    
    # Create payment
    payment = Payment(
        user_id=user_id,
        tariff_id=tariff_id,
        amount=Decimal(tariff.price_stars),  # Store Stars amount
        currency="XTR",  # Telegram Stars currency code
        checks_count=tariff.checks_count,
        payment_method=PaymentMethodEnum.TELEGRAM_STARS,
        status=PaymentStatusEnum.PENDING,
    )
    session.add(payment)
    await session.flush()  # Get payment_id
    
    # Log event
    await log_payment_event(
        session=session,
        payment_id=payment.payment_id,
        event_type=PaymentEventTypeEnum.CREATED,
        status_after=PaymentStatusEnum.PENDING.value,
        details={
            "user_id": user_id,
            "tariff_id": str(tariff_id),
            "tariff_name": tariff.name,
            "price_stars": tariff.price_stars,
            "checks_count": tariff.checks_count,
        },
    )
    
    await session.commit()
    await session.refresh(payment)
    
    logger.info(
        f"Created Telegram Stars payment: payment_id={payment.payment_id}, "
        f"user_id={user_id}, tariff={tariff.name}, price={tariff.price_stars} XTR"
    )
    
    return payment, tariff


async def validate_telegram_stars_payment(
    session: AsyncSession,
    payment_id: uuid.UUID,
    expected_amount: int,
) -> Payment:
    """Validate a Telegram Stars payment before checkout.
    
    Args:
        session: Database session
        payment_id: Payment UUID
        expected_amount: Expected amount in Stars
        
    Returns:
        Payment if valid
        
    Raises:
        PaymentNotFoundError: If payment doesn't exist
        PaymentAlreadyCompletedError: If already completed
        PaymentAmountMismatchError: If amount doesn't match
        PaymentInvalidStatusError: If status is not PENDING
    """
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        logger.warning(f"Payment {payment_id} not found for validation")
        raise PaymentNotFoundError(f"Payment {payment_id} not found")
    
    if payment.status == PaymentStatusEnum.COMPLETED:
        logger.warning(f"Payment {payment_id} already completed")
        raise PaymentAlreadyCompletedError(f"Payment {payment_id} already completed")
    
    if payment.status != PaymentStatusEnum.PENDING:
        logger.warning(f"Payment {payment_id} has invalid status: {payment.status}")
        raise PaymentInvalidStatusError(
            f"Payment {payment_id} has invalid status: {payment.status}"
        )
    
    # Verify amount matches
    if int(payment.amount) != expected_amount:
        logger.warning(
            f"Payment {payment_id} amount mismatch: "
            f"expected={expected_amount}, actual={payment.amount}"
        )
        raise PaymentAmountMismatchError(
            f"Expected {expected_amount} XTR, but payment is for {payment.amount} XTR"
        )
    
    # Log pre-checkout event
    await log_payment_event(
        session=session,
        payment_id=payment_id,
        event_type=PaymentEventTypeEnum.PRE_CHECKOUT,
        status_before=payment.status.value,
        status_after=payment.status.value,
        details={"expected_amount": expected_amount},
    )
    await session.commit()
    
    logger.info(f"Payment {payment_id} validated for pre-checkout")
    
    return payment


async def complete_telegram_stars_payment(
    session: AsyncSession,
    payment_id: uuid.UUID,
    telegram_payment_charge_id: str,
    total_amount: int,
) -> tuple[Payment, User]:
    """Complete a Telegram Stars payment.
    
    Args:
        session: Database session
        payment_id: Payment UUID
        telegram_payment_charge_id: Charge ID from Telegram
        total_amount: Total amount paid in Stars
        
    Returns:
        Tuple of (Payment, User) with updated balances
        
    Raises:
        PaymentNotFoundError: If payment doesn't exist
        PaymentAlreadyCompletedError: If already completed with same charge_id (idempotent)
        PaymentAmountMismatchError: If amount doesn't match
        UserNotFoundError: If user doesn't exist
    """
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        logger.error(f"Payment {payment_id} not found for completion")
        raise PaymentNotFoundError(f"Payment {payment_id} not found")
    
    # Idempotency check - if already completed with same charge_id, return success
    if payment.status == PaymentStatusEnum.COMPLETED:
        if payment.telegram_payment_charge_id == telegram_payment_charge_id:
            logger.info(
                f"Payment {payment_id} already completed with same charge_id, "
                f"returning idempotent response"
            )
            # Get user for balance
            user_result = await session.execute(
                select(User).where(User.user_id == payment.user_id)
            )
            user = user_result.scalar_one_or_none()
            return payment, user
        else:
            logger.error(
                f"Payment {payment_id} already completed with different charge_id: "
                f"existing={payment.telegram_payment_charge_id}, new={telegram_payment_charge_id}"
            )
            raise PaymentAlreadyCompletedError(
                f"Payment {payment_id} already completed with different charge"
            )
    
    # Verify amount matches
    if int(payment.amount) != total_amount:
        logger.error(
            f"Payment {payment_id} amount mismatch: "
            f"expected={payment.amount}, received={total_amount}"
        )
        # Log failed event
        await log_payment_event(
            session=session,
            payment_id=payment_id,
            event_type=PaymentEventTypeEnum.FAILED,
            status_before=payment.status.value,
            status_after=PaymentStatusEnum.FAILED.value,
            error_message=f"Amount mismatch: expected {payment.amount}, received {total_amount}",
        )
        payment.status = PaymentStatusEnum.FAILED
        await session.commit()
        raise PaymentAmountMismatchError(
            f"Expected {payment.amount} XTR, received {total_amount} XTR"
        )
    
    # Get user
    user_result = await session.execute(
        select(User).where(User.user_id == payment.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        logger.error(f"User {payment.user_id} not found for payment {payment_id}")
        raise UserNotFoundError(f"User {payment.user_id} not found")
    
    # Update payment
    old_status = payment.status.value
    old_balance = user.checks_balance
    
    payment.status = PaymentStatusEnum.COMPLETED
    payment.telegram_payment_charge_id = telegram_payment_charge_id
    payment.completed_at = datetime.now(timezone.utc)
    
    # Add checks to user balance
    user.checks_balance += payment.checks_count
    
    # Log completion event
    await log_payment_event(
        session=session,
        payment_id=payment_id,
        event_type=PaymentEventTypeEnum.COMPLETED,
        status_before=old_status,
        status_after=PaymentStatusEnum.COMPLETED.value,
        details={
            "telegram_payment_charge_id": telegram_payment_charge_id,
            "total_amount": total_amount,
            "checks_added": payment.checks_count,
            "balance_before": old_balance,
            "balance_after": user.checks_balance,
        },
    )
    
    await session.commit()
    await session.refresh(payment)
    await session.refresh(user)
    
    logger.info(
        f"Telegram Stars payment completed: payment_id={payment_id}, "
        f"charge_id={telegram_payment_charge_id}, "
        f"user={payment.user_id}, checks_added={payment.checks_count}, "
        f"balance: {old_balance} -> {user.checks_balance}"
    )
    
    return payment, user


async def fail_telegram_stars_payment(
    session: AsyncSession,
    payment_id: uuid.UUID,
    error_reason: str,
    error_message: str | None = None,
) -> Payment:
    """Mark a Telegram Stars payment as failed.
    
    Args:
        session: Database session
        payment_id: Payment UUID
        error_reason: Short reason for failure
        error_message: Detailed error message
        
    Returns:
        Updated Payment
        
    Raises:
        PaymentNotFoundError: If payment doesn't exist
        PaymentAlreadyCompletedError: If already completed
    """
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        logger.error(f"Payment {payment_id} not found for failure marking")
        raise PaymentNotFoundError(f"Payment {payment_id} not found")
    
    if payment.status == PaymentStatusEnum.COMPLETED:
        logger.warning(f"Cannot fail completed payment {payment_id}")
        raise PaymentAlreadyCompletedError(f"Payment {payment_id} is already completed")
    
    old_status = payment.status.value
    payment.status = PaymentStatusEnum.FAILED
    
    # Log failure event
    await log_payment_event(
        session=session,
        payment_id=payment_id,
        event_type=PaymentEventTypeEnum.FAILED,
        status_before=old_status,
        status_after=PaymentStatusEnum.FAILED.value,
        details={"error_reason": error_reason},
        error_message=error_message,
    )
    
    await session.commit()
    await session.refresh(payment)
    
    logger.warning(
        f"Telegram Stars payment failed: payment_id={payment_id}, "
        f"reason={error_reason}, message={error_message}"
    )
    
    return payment


async def get_payment_with_events(
    session: AsyncSession,
    payment_id: uuid.UUID,
) -> tuple[Payment | None, list[PaymentEvent]]:
    """Get payment with all its events.
    
    Args:
        session: Database session
        payment_id: Payment UUID
        
    Returns:
        Tuple of (Payment or None, list of PaymentEvents)
    """
    payment_result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = payment_result.scalar_one_or_none()
    
    events_result = await session.execute(
        select(PaymentEvent)
        .where(PaymentEvent.payment_id == payment_id)
        .order_by(PaymentEvent.created_at.asc())
    )
    events = list(events_result.scalars().all())
    
    return payment, events

