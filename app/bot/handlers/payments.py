"""Telegram bot payment handlers for Telegram Stars."""

import uuid

import httpx
from aiogram import F, Router
from aiogram.enums import ContentType
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery

from app.config import get_settings
from app.utils.logger import logger

router = Router()
settings = get_settings()


def get_api_url(path: str) -> str:
    """Get full API URL."""
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1{path}"


# --- Pre-checkout Query Handler ---


@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout: PreCheckoutQuery):
    """Handle pre-checkout query from Telegram.
    
    This is called by Telegram before processing a payment.
    Must respond within 10 seconds.
    """
    payment_id_str = pre_checkout.invoice_payload
    total_amount = pre_checkout.total_amount
    
    logger.info(
        f"Pre-checkout query received: payment_id={payment_id_str}, "
        f"amount={total_amount}, user={pre_checkout.from_user.id}"
    )
    
    # Validate payment_id format
    try:
        payment_id = uuid.UUID(payment_id_str)
    except ValueError:
        logger.error(f"Invalid payment_id format in pre-checkout: {payment_id_str}")
        await pre_checkout.answer(
            ok=False,
            error_message="Неверный идентификатор платежа",
        )
        return
    
    # Validate payment via API
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:  # 8 seconds to stay within Telegram's 10s limit
            response = await client.post(
                get_api_url(f"/payments/telegram-stars/validate/{payment_id}"),
                params={"expected_amount": total_amount},
            )
            
            if response.status_code == 200:
                logger.info(f"Payment {payment_id} validated for pre-checkout")
                await pre_checkout.answer(ok=True)
            else:
                error_detail = response.json().get("detail", "Ошибка валидации платежа")
                logger.warning(f"Payment validation failed: {error_detail}")
                await pre_checkout.answer(
                    ok=False,
                    error_message=error_detail[:200],  # Telegram limits error message
                )
                
    except httpx.TimeoutException:
        logger.error(f"Timeout validating payment {payment_id}")
        await pre_checkout.answer(
            ok=False,
            error_message="Превышено время ожидания. Попробуйте снова.",
        )
    except Exception as e:
        logger.error(f"Error validating payment {payment_id}: {e}")
        await pre_checkout.answer(
            ok=False,
            error_message="Ошибка при проверке платежа",
        )


# --- Successful Payment Handler ---


@router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    """Handle successful payment from Telegram.
    
    This is called after user completes the payment.
    """
    payment_data = message.successful_payment
    payment_id_str = payment_data.invoice_payload
    telegram_payment_charge_id = payment_data.telegram_payment_charge_id
    total_amount = payment_data.total_amount
    currency = payment_data.currency
    
    logger.info(
        f"Successful payment received: payment_id={payment_id_str}, "
        f"charge_id={telegram_payment_charge_id}, "
        f"amount={total_amount} {currency}, user={message.from_user.id}"
    )
    
    # Validate payment_id format
    try:
        payment_id = uuid.UUID(payment_id_str)
    except ValueError:
        logger.error(f"Invalid payment_id in successful_payment: {payment_id_str}")
        await message.answer(
            "❌ Ошибка обработки платежа. Обратитесь в поддержку с кодом: INVALID_ID"
        )
        return
    
    # Complete payment via API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                get_api_url("/payments/telegram-stars/complete"),
                json={
                    "payment_id": str(payment_id),
                    "telegram_payment_charge_id": telegram_payment_charge_id,
                    "total_amount": total_amount,
                },
            )
            
            if response.status_code == 200:
                result = response.json()
                checks_added = result.get("checks_added", 0)
                new_balance = result.get("user_checks_balance", 0)
                
                logger.info(
                    f"Payment {payment_id} completed via API. "
                    f"Checks added: {checks_added}, New balance: {new_balance}"
                )
                
                # Send confirmation to user
                await message.answer(
                    f"✅ <b>Оплата успешно получена!</b>\n\n"
                    f"Сумма: {total_amount} ⭐\n"
                    f"Начислено проверок: <b>{checks_added}</b>\n"
                    f"Ваш баланс: <b>{new_balance}</b> проверок\n\n"
                    f"Теперь вы можете использовать команду /check для проверки аккаунтов.",
                )
                
            elif response.status_code == 409:
                # Payment already completed (idempotent case)
                logger.warning(f"Payment {payment_id} already completed")
                await message.answer(
                    "✅ Этот платеж уже был обработан.\n\n"
                    "Используйте /balance для проверки баланса."
                )
                
            else:
                error_detail = response.json().get("detail", "Unknown error")
                logger.error(
                    f"Error completing payment {payment_id}: "
                    f"status={response.status_code}, detail={error_detail}"
                )
                await message.answer(
                    f"❌ Ошибка при обработке платежа.\n\n"
                    f"Код платежа: <code>{payment_id_str[:8]}...</code>\n"
                    f"Пожалуйста, обратитесь в поддержку."
                )
                
    except httpx.TimeoutException:
        logger.error(f"Timeout completing payment {payment_id}")
        await message.answer(
            f"⏳ Обработка платежа занимает больше времени.\n\n"
            f"Код платежа: <code>{payment_id_str[:8]}...</code>\n"
            f"Баланс будет обновлен в ближайшее время."
        )
    except Exception as e:
        logger.error(f"Exception completing payment {payment_id}: {e}")
        await message.answer(
            f"❌ Произошла ошибка при обработке платежа.\n\n"
            f"Код платежа: <code>{payment_id_str[:8]}...</code>\n"
            f"Пожалуйста, обратитесь в поддержку."
        )


# --- Helper Functions for Invoice Creation ---


async def send_stars_invoice(
    message: Message,
    payment_id: uuid.UUID,
    tariff_name: str,
    tariff_description: str | None,
    checks_count: int,
    price_stars: int,
):
    """Send invoice for Telegram Stars payment.
    
    Args:
        message: Message to reply to
        payment_id: Payment UUID to use as payload
        tariff_name: Name of tariff
        tariff_description: Description of tariff
        checks_count: Number of checks in package
        price_stars: Price in Stars
    """
    prices = [
        LabeledPrice(
            label=f"{checks_count} проверок",
            amount=price_stars,  # Telegram Stars uses direct amount, not *100
        )
    ]
    
    description = tariff_description or f"Пакет проверок для анализа Instagram аккаунтов"
    
    await message.bot.send_invoice(
        chat_id=message.chat.id,
        title=f"Пакет проверок: {tariff_name}",
        description=description[:255],  # Telegram limits description
        payload=str(payment_id),  # Used to identify payment later
        currency="XTR",  # Telegram Stars currency code
        prices=prices,
        # provider_token is not needed for Telegram Stars
    )
    
    logger.info(
        f"Invoice sent for payment {payment_id}: "
        f"tariff={tariff_name}, price={price_stars} XTR, user={message.from_user.id}"
    )

