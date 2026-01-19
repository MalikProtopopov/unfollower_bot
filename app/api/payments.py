"""FastAPI router for payment endpoints with Robokassa integration."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_session
from app.models.models import Payment, PaymentMethodEnum, PaymentStatusEnum, Tariff, User
from app.models.schemas import (
    PaymentCreateRequest,
    PaymentEventResponse,
    PaymentEventsListResponse,
    PaymentResponse,
    TelegramStarsPaymentCompleteRequest,
    TelegramStarsPaymentCompleteResponse,
    TelegramStarsPaymentCreateRequest,
    TelegramStarsPaymentCreateResponse,
    TelegramStarsPaymentFailedRequest,
    TelegramStarsPaymentFailedResponse,
)
from app.services.admin_notification_service import notify_admin
from app.services.payment_service import (
    PaymentAlreadyCompletedError,
    PaymentAmountMismatchError,
    PaymentInvalidStatusError,
    PaymentNotFoundError,
    TariffNotAvailableError,
    TariffNotFoundError,
    UserNotFoundError,
    complete_telegram_stars_payment,
    create_telegram_stars_payment,
    fail_telegram_stars_payment,
    get_payment_with_events,
    validate_telegram_stars_payment,
)
from app.services.notification_service import TelegramNotifier
from app.utils.logger import logger
from app.utils.robokassa import (
    format_callback_response,
    generate_payment_url,
    verify_amount,
    verify_callback_signature,
)

router = APIRouter(prefix="/payments", tags=["payments"])
settings = get_settings()


@router.post("/create", response_model=PaymentResponse)
async def create_payment(
    request: PaymentCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new payment for a tariff.
    
    Returns payment details including Robokassa payment URL if applicable.
    """
    # Verify user exists
    user_result = await session.execute(
        select(User).where(User.user_id == request.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {request.user_id} not found",
        )
    
    # Verify tariff exists and is active
    tariff_result = await session.execute(
        select(Tariff).where(Tariff.tariff_id == request.tariff_id)
    )
    tariff = tariff_result.scalar_one_or_none()
    
    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tariff {request.tariff_id} not found",
        )
    
    if not tariff.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This tariff is no longer available",
        )
    
    # Determine amount based on payment method
    if request.payment_method == PaymentMethodEnum.TELEGRAM_STARS:
        if not tariff.price_stars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This tariff is not available for Telegram Stars payment",
            )
        amount = tariff.price_stars
        currency = "XTR"  # Telegram Stars currency code
    else:
        amount = tariff.price_rub
        currency = "RUB"
    
    # Create payment record
    payment = Payment(
        user_id=request.user_id,
        tariff_id=request.tariff_id,
        amount=amount,
        currency=currency,
        checks_count=tariff.checks_count,
        payment_method=request.payment_method,
        status=PaymentStatusEnum.PENDING,
    )
    
    # Generate Robokassa URL if needed
    if request.payment_method == PaymentMethodEnum.ROBOKASSA:
        payment.robokassa_invoice_id = str(payment.payment_id)
        
        # Check if Robokassa is configured
        if not settings.robokassa_merchant_login or not settings.robokassa_password_1:
            logger.warning("Robokassa not configured, using stub URL")
            payment.robokassa_payment_url = f"https://auth.robokassa.ru/Merchant/Index.aspx?InvId={payment.payment_id}&OutSum={amount}&Description={tariff.name}"
        else:
            payment.robokassa_payment_url = generate_payment_url(
                merchant_login=settings.robokassa_merchant_login,
                password_1=settings.robokassa_password_1,
                inv_id=str(payment.payment_id),
                out_sum=payment.amount,
                description=f"Пакет '{tariff.name}' - {tariff.checks_count} проверок",
                user_id=request.user_id,
                tariff_id=str(request.tariff_id),
                test_mode=settings.robokassa_test_mode,
            )
    
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    
    logger.info(
        f"Created payment {payment.payment_id} for user {request.user_id}: "
        f"{tariff.checks_count} checks, {amount} {currency}"
    )
    
    return PaymentResponse(
        payment_id=payment.payment_id,
        user_id=payment.user_id,
        tariff_id=payment.tariff_id,
        amount=payment.amount,
        currency=payment.currency,
        checks_count=payment.checks_count,
        payment_method=payment.payment_method,
        status=payment.status,
        robokassa_payment_url=payment.robokassa_payment_url,
        created_at=payment.created_at,
        completed_at=payment.completed_at,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get payment details by ID."""
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found",
        )
    
    return PaymentResponse(
        payment_id=payment.payment_id,
        user_id=payment.user_id,
        tariff_id=payment.tariff_id,
        amount=payment.amount,
        currency=payment.currency,
        checks_count=payment.checks_count,
        payment_method=payment.payment_method,
        status=payment.status,
        robokassa_payment_url=payment.robokassa_payment_url,
        created_at=payment.created_at,
        completed_at=payment.completed_at,
    )


@router.post("/robokassa/callback", response_class=PlainTextResponse)
async def robokassa_callback(
    OutSum: str = Form(...),
    InvId: str = Form(...),
    SignatureValue: str = Form(...),
    Shp_payment_id: str = Form(None),
    Shp_user_id: str = Form(None),
    Shp_tariff_id: str = Form(None),
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    """Handle Robokassa payment callback (Result URL).
    
    This endpoint is called by Robokassa after successful payment.
    Must return OK{InvId} on success.
    """
    logger.info(
        f"Robokassa callback received: InvId={InvId}, OutSum={OutSum}, "
        f"Shp_payment_id={Shp_payment_id}, Shp_user_id={Shp_user_id}"
    )
    
    # Build Shp params dict for signature verification
    shp_params = {}
    if Shp_payment_id:
        shp_params["Shp_payment_id"] = Shp_payment_id
    if Shp_tariff_id:
        shp_params["Shp_tariff_id"] = Shp_tariff_id
    if Shp_user_id:
        shp_params["Shp_user_id"] = Shp_user_id
    
    # 1. Verify signature (CRITICAL for security)
    if settings.robokassa_password_2:
        is_valid = verify_callback_signature(
            out_sum=OutSum,
            inv_id=InvId,
            signature=SignatureValue,
            password_2=settings.robokassa_password_2,
            shp_params=shp_params,
        )
        
        if not is_valid:
            logger.error(f"Invalid signature for callback InvId={InvId}")
            # Notify admin about potential fraud attempt
            await notify_admin(
                f"⚠️ Подозрительный callback Robokassa!\n\n"
                f"InvId: {InvId}\n"
                f"OutSum: {OutSum}\n"
                f"Подпись не прошла проверку!"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature",
            )
    else:
        logger.warning("Robokassa Password #2 not configured, skipping signature verification")
    
    # 2. Find payment by invoice ID
    payment_id = Shp_payment_id or InvId
    
    try:
        payment_uuid = uuid.UUID(payment_id)
    except ValueError:
        logger.error(f"Invalid payment_id format: {payment_id}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment ID format",
        )
    
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_uuid)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        logger.error(f"Payment not found for InvId: {InvId}, payment_id: {payment_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found",
        )
    
    # 3. Check idempotency - payment already processed
    if payment.status == PaymentStatusEnum.COMPLETED:
        logger.warning(f"Payment {payment.payment_id} already completed, returning OK")
        return format_callback_response(InvId)
    
    # 4. Verify amount matches
    if not verify_amount(payment.amount, OutSum):
        logger.error(
            f"Amount mismatch for payment {payment.payment_id}: "
            f"expected={payment.amount}, received={OutSum}"
        )
        await notify_admin(
            f"⚠️ Несовпадение суммы платежа!\n\n"
            f"Payment ID: {payment.payment_id}\n"
            f"User ID: {payment.user_id}\n"
            f"Ожидалось: {payment.amount} RUB\n"
            f"Получено: {OutSum} RUB"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount mismatch",
        )
    
    # 5. Update payment status
    payment.status = PaymentStatusEnum.COMPLETED
    payment.completed_at = datetime.now(timezone.utc)
    
    # 6. Add checks to user's balance
    user_result = await session.execute(
        select(User).where(User.user_id == payment.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if user:
        old_balance = user.checks_balance
        user.checks_balance += payment.checks_count
        
        logger.info(
            f"Payment {payment.payment_id} completed. "
            f"Added {payment.checks_count} checks to user {user.user_id}. "
            f"Balance: {old_balance} -> {user.checks_balance}"
        )
        
        # 7. Notify admin about successful payment
        await notify_admin(
            f"💰 Новая оплата!\n\n"
            f"User: {user.user_id} (@{user.username or 'N/A'})\n"
            f"Сумма: {OutSum} RUB\n"
            f"Проверок: +{payment.checks_count}\n"
            f"Новый баланс: {user.checks_balance}"
        )
        
        # 8. Notify user about successful payment
        try:
            notifier = TelegramNotifier()
            await notifier.send_message(
                user_id=payment.user_id,
                text=(
                    f"✅ Оплата успешно получена!\n\n"
                    f"Сумма: {OutSum} ₽\n"
                    f"Начислено проверок: {payment.checks_count}\n"
                    f"Ваш баланс: {user.checks_balance} проверок\n\n"
                    f"Теперь вы можете использовать команду /check для проверки аккаунтов."
                ),
            )
        except Exception as e:
            logger.error(f"Failed to notify user {payment.user_id} about payment: {e}")
    
    await session.commit()
    
    # Return success response for Robokassa
    return format_callback_response(InvId)


@router.get("/robokassa/success", response_class=HTMLResponse)
async def robokassa_success(
    InvId: str = None,
    OutSum: str = None,
):
    """Handle Robokassa success redirect.
    
    User is redirected here after successful payment.
    """
    bot_link = f"https://t.me/{settings.bot_username}" if settings.bot_username else "#"
    
    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Оплата успешна</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 400px;
                }}
                .success-icon {{
                    font-size: 64px;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #333;
                    margin-bottom: 15px;
                }}
                p {{
                    color: #666;
                    line-height: 1.6;
                    margin-bottom: 25px;
                }}
                .amount {{
                    font-size: 24px;
                    font-weight: bold;
                    color: #4CAF50;
                    margin: 15px 0;
                }}
                .btn {{
                    display: inline-block;
                    background: #0088cc;
                    color: white;
                    padding: 15px 40px;
                    text-decoration: none;
                    border-radius: 50px;
                    font-weight: bold;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 20px rgba(0,136,204,0.4);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Оплата успешна!</h1>
                {f'<div class="amount">{OutSum} ₽</div>' if OutSum else ''}
                <p>Спасибо за покупку! Проверки уже начислены на ваш баланс.</p>
                <p>Вернитесь в Telegram бот для продолжения работы.</p>
                <a href="{bot_link}" class="btn">Открыть бот</a>
            </div>
        </body>
        </html>
        """,
        status_code=200,
    )


@router.get("/robokassa/fail", response_class=HTMLResponse)
async def robokassa_fail(
    InvId: str = None,
    OutSum: str = None,
):
    """Handle Robokassa fail redirect.
    
    User is redirected here if payment fails or is cancelled.
    """
    bot_link = f"https://t.me/{settings.bot_username}" if settings.bot_username else "#"
    
    return HTMLResponse(
        content=f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Оплата не удалась</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                }}
                .container {{
                    background: white;
                    padding: 40px;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 400px;
                }}
                .fail-icon {{
                    font-size: 64px;
                    margin-bottom: 20px;
                }}
                h1 {{
                    color: #333;
                    margin-bottom: 15px;
                }}
                p {{
                    color: #666;
                    line-height: 1.6;
                    margin-bottom: 25px;
                }}
                .btn {{
                    display: inline-block;
                    background: #0088cc;
                    color: white;
                    padding: 15px 40px;
                    text-decoration: none;
                    border-radius: 50px;
                    font-weight: bold;
                    transition: transform 0.2s, box-shadow 0.2s;
                }}
                .btn:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 5px 20px rgba(0,136,204,0.4);
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="fail-icon">❌</div>
                <h1>Оплата не удалась</h1>
                <p>К сожалению, платеж не был завершен. Это может произойти по разным причинам.</p>
                <p>Вы можете попробовать снова или связаться с поддержкой.</p>
                <a href="{bot_link}" class="btn">Вернуться в бот</a>
            </div>
        </body>
        </html>
        """,
        status_code=200,
    )


@router.post("/complete/{payment_id}")
async def complete_payment_manually(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Manually complete a payment (for testing or manual payments).
    
    TODO: Add admin verification in production.
    """
    result = await session.execute(
        select(Payment).where(Payment.payment_id == payment_id)
    )
    payment = result.scalar_one_or_none()
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found",
        )
    
    if payment.status == PaymentStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment already completed",
        )
    
    # Update payment status
    payment.status = PaymentStatusEnum.COMPLETED
    payment.completed_at = datetime.now(timezone.utc)
    
    # Add checks to user's balance
    user_result = await session.execute(
        select(User).where(User.user_id == payment.user_id)
    )
    user = user_result.scalar_one_or_none()
    
    if user:
        user.checks_balance += payment.checks_count
        logger.info(
            f"Payment {payment.payment_id} manually completed. "
            f"Added {payment.checks_count} checks to user {user.user_id}. "
            f"New balance: {user.checks_balance}"
        )
    
    await session.commit()
    
    return {
        "message": "Payment completed successfully",
        "payment_id": str(payment_id),
        "checks_added": payment.checks_count,
        "new_balance": user.checks_balance if user else None,
    }


@router.get("/user/{user_id}/history")
async def get_user_payments(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 10,
    offset: int = 0,
):
    """Get payment history for a user."""
    result = await session.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    payments = result.scalars().all()
    
    return {
        "payments": [
            PaymentResponse(
                payment_id=p.payment_id,
                user_id=p.user_id,
                tariff_id=p.tariff_id,
                amount=p.amount,
                currency=p.currency,
                checks_count=p.checks_count,
                payment_method=p.payment_method,
                status=p.status,
                robokassa_payment_url=p.robokassa_payment_url,
                created_at=p.created_at,
                completed_at=p.completed_at,
            )
            for p in payments
        ],
        "total": len(payments),
    }


# --- Telegram Stars Payment Endpoints ---


@router.post("/telegram-stars/create", response_model=TelegramStarsPaymentCreateResponse)
async def create_telegram_stars_payment_endpoint(
    request: TelegramStarsPaymentCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new Telegram Stars payment.
    
    Returns payment details needed for sending invoice via Telegram Bot API.
    """
    try:
        payment, tariff = await create_telegram_stars_payment(
            session=session,
            user_id=request.user_id,
            tariff_id=request.tariff_id,
        )
        
        return TelegramStarsPaymentCreateResponse(
            payment_id=payment.payment_id,
            user_id=payment.user_id,
            tariff_id=tariff.tariff_id,
            tariff_name=tariff.name,
            tariff_description=tariff.description,
            checks_count=tariff.checks_count,
            price_stars=tariff.price_stars,
            currency="XTR",
            status=payment.status,
            created_at=payment.created_at,
        )
        
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except TariffNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except TariffNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/telegram-stars/validate/{payment_id}")
async def validate_telegram_stars_payment_endpoint(
    payment_id: uuid.UUID,
    expected_amount: int,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Validate a Telegram Stars payment before pre-checkout.
    
    Called by bot during pre_checkout_query to verify payment is valid.
    """
    try:
        payment = await validate_telegram_stars_payment(
            session=session,
            payment_id=payment_id,
            expected_amount=expected_amount,
        )
        
        return {
            "valid": True,
            "payment_id": str(payment.payment_id),
            "status": payment.status.value,
        }
        
    except PaymentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PaymentAlreadyCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PaymentAmountMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PaymentInvalidStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/telegram-stars/complete", response_model=TelegramStarsPaymentCompleteResponse)
async def complete_telegram_stars_payment_endpoint(
    request: TelegramStarsPaymentCompleteRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Complete a Telegram Stars payment after successful payment.
    
    Called by bot after receiving successful_payment message.
    Adds checks to user balance and marks payment as completed.
    """
    try:
        payment, user = await complete_telegram_stars_payment(
            session=session,
            payment_id=request.payment_id,
            telegram_payment_charge_id=request.telegram_payment_charge_id,
            total_amount=request.total_amount,
        )
        
        # Notify admin about successful Stars payment
        await notify_admin(
            f"💰 Новая оплата через Telegram Stars!\n\n"
            f"User: {user.user_id} (@{user.username or 'N/A'})\n"
            f"Сумма: {request.total_amount} ⭐\n"
            f"Проверок: +{payment.checks_count}\n"
            f"Новый баланс: {user.checks_balance}"
        )
        
        return TelegramStarsPaymentCompleteResponse(
            payment_id=payment.payment_id,
            status=payment.status,
            checks_added=payment.checks_count,
            user_checks_balance=user.checks_balance,
            completed_at=payment.completed_at,
        )
        
    except PaymentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PaymentAlreadyCompletedError as e:
        # This is actually idempotent - return success
        logger.warning(f"Payment already completed: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except PaymentAmountMismatchError as e:
        # Notify admin about suspicious activity
        await notify_admin(
            f"⚠️ Несовпадение суммы платежа Stars!\n\n"
            f"Payment ID: {request.payment_id}\n"
            f"Получено: {request.total_amount} XTR\n"
            f"Ошибка: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except UserNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post("/telegram-stars/failed", response_model=TelegramStarsPaymentFailedResponse)
async def fail_telegram_stars_payment_endpoint(
    request: TelegramStarsPaymentFailedRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Mark a Telegram Stars payment as failed.
    
    Called when payment fails or is cancelled.
    """
    try:
        payment = await fail_telegram_stars_payment(
            session=session,
            payment_id=request.payment_id,
            error_reason=request.error_reason,
            error_message=request.error_message,
        )
        
        # Notify admin about failed payment
        await notify_admin(
            f"⚠️ Неудачный платёж Telegram Stars\n\n"
            f"Payment ID: {request.payment_id}\n"
            f"Причина: {request.error_reason}\n"
            f"Сообщение: {request.error_message or 'N/A'}"
        )
        
        return TelegramStarsPaymentFailedResponse(
            payment_id=payment.payment_id,
            status=payment.status,
            error_reason=request.error_reason,
        )
        
    except PaymentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except PaymentAlreadyCompletedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/{payment_id}/events", response_model=PaymentEventsListResponse)
async def get_payment_events(
    payment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get all events for a payment (for admin/audit purposes)."""
    payment, events = await get_payment_with_events(session, payment_id)
    
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment {payment_id} not found",
        )
    
    return PaymentEventsListResponse(
        events=[
            PaymentEventResponse(
                event_id=e.event_id,
                payment_id=e.payment_id,
                event_type=e.event_type.value,
                status_before=e.status_before,
                status_after=e.status_after,
                details=e.details,
                error_message=e.error_message,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=len(events),
    )
