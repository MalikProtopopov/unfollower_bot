"""Balance and buy command handlers."""

from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User

from app.bot.http_client import APIError, APINotFoundError, api_get, api_post
from app.bot.keyboards import (
    get_back_to_main_keyboard,
    get_buy_balance_keyboard,
    build_tariffs_keyboard,
)
from app.utils.logger import logger

router = Router()


# --- /balance command ---


@router.message(Command("balance"))
async def cmd_balance(message: Message, user: Optional[User] = None) -> None:
    """Handle /balance command - show user's check balance."""
    if user is None:
        user = message.from_user
    user_id = user.id

    try:
        result = await api_get(f"/users/{user_id}/balance")

        logger.info(
            f"Balance API response for user {user_id}: "
            f"checks_balance={result.get('checks_balance')}, "
            f"referral_code={result.get('referral_code')}"
        )

        balance = result.get("checks_balance", 0)

        text = f"""
💰 <b>Баланс проверок</b>

У вас: <b>{balance}</b> проверок

"""
        if balance == 0:
            text += "⚠️ Для проверки нужно пополнить баланс.\nИспользуйте /buy для покупки."
        else:
            text += "Используйте /check чтобы проверить аккаунт."

        await message.answer(text, reply_markup=get_buy_balance_keyboard())

    except APINotFoundError:
        # User doesn't exist yet
        await message.answer(
            "💰 <b>Баланс проверок</b>\n\n"
            "У вас: <b>0</b> проверок\n\n"
            "Для проверки нужно пополнить баланс или пригласить друзей.",
            reply_markup=get_buy_balance_keyboard(),
        )

    except APIError as e:
        logger.error(f"Error in /balance command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# --- /buy command ---


@router.message(Command("buy"))
async def cmd_buy(message: Message) -> None:
    """Handle /buy command - show available tariffs."""
    await show_tariffs(message)


async def show_tariffs(message: Message, user: Optional[User] = None) -> None:
    """Show available tariffs for purchase."""
    try:
        result = await api_get("/tariffs")
        tariffs = result.get("tariffs", [])

        logger.info(
            f"Tariffs loaded: total={len(tariffs)}, " f"names={[t.get('name') for t in tariffs]}"
        )

        if not tariffs:
            await message.answer(
                "🛒 <b>Покупка проверок</b>\n\n" "В данный момент нет доступных тарифов.",
                reply_markup=get_back_to_main_keyboard(),
            )
            return

        text = "🛒 <b>Покупка проверок</b>\n\nВыберите тариф:\n\n"

        for tariff in tariffs:
            name = tariff["name"]
            checks = tariff["checks_count"]
            price_stars = tariff.get("price_stars")

            if price_stars:
                text += f"📦 <b>{name}</b>\n"
                text += f"   {checks} проверок — {price_stars}⭐\n\n"

        text += "👥 Или пригласите 10 друзей и получите 1 проверку бесплатно!"

        keyboard = build_tariffs_keyboard(tariffs)
        await message.answer(text, reply_markup=keyboard)

    except APIError as e:
        logger.error(f"Error in /buy command: {e}")
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_back_to_main_keyboard(),
        )


# --- Callbacks ---


@router.callback_query(F.data == "balance")
async def callback_balance(callback: CallbackQuery) -> None:
    """Handle balance button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    # Pass the actual user who clicked, not the message author (which is the bot)
    await cmd_balance(callback.message, user=callback.from_user)


@router.callback_query(F.data == "buy")
async def callback_buy(callback: CallbackQuery) -> None:
    """Handle buy button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    # Pass the actual user who clicked for consistent logging
    await show_tariffs(callback.message, user=callback.from_user)


# --- Buy tariff callback ---


@router.callback_query(F.data.startswith("buy_tariff:"))
async def callback_buy_tariff(callback: CallbackQuery) -> None:
    """Handle tariff purchase button."""
    await callback.answer()

    # Parse callback data: buy_tariff:{tariff_id}:{payment_type}
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer(
            "❌ Ошибка: неверные данные",
            reply_markup=get_back_to_main_keyboard(),
        )
        return

    tariff_id = parts[1]
    payment_type = parts[2]  # 'rub' or 'stars'
    user_id = callback.from_user.id

    if payment_type == "stars":
        # Create payment and send invoice for Telegram Stars
        try:
            result = await api_post(
                "/payments/telegram-stars/create",
                json={
                    "user_id": user_id,
                    "tariff_id": tariff_id,
                },
            )

            payment_id = result["payment_id"]
            tariff_name = result["tariff_name"]
            tariff_description = result.get("tariff_description")
            checks_count = result["checks_count"]
            price_stars = result["price_stars"]

            # Import and send invoice
            from app.bot.handlers.payments import send_stars_invoice

            await send_stars_invoice(
                message=callback.message,
                payment_id=payment_id,
                tariff_name=tariff_name,
                tariff_description=tariff_description,
                checks_count=checks_count,
                price_stars=price_stars,
            )

            logger.info(
                f"Stars invoice sent for user {user_id}, " f"tariff={tariff_name}, price={price_stars}"
            )

        except APINotFoundError as e:
            await callback.message.answer(
                f"❌ {e.detail or 'Тариф не найден'}",
                reply_markup=get_back_to_main_keyboard(),
            )

        except APIError as e:
            if e.status_code == 400:
                await callback.message.answer(
                    f"❌ {e.detail or 'Тариф недоступен'}",
                    reply_markup=get_back_to_main_keyboard(),
                )
            else:
                logger.error(f"Error creating Stars payment: {e}")
                await callback.message.answer(
                    "❌ Не удалось создать платёж.\n" "Пожалуйста, попробуйте позже.",
                    reply_markup=get_back_to_main_keyboard(),
                )

        except Exception as e:
            logger.error(f"Error creating Stars payment for user {user_id}: {e}")
            await callback.message.answer(
                "❌ Произошла ошибка.\n" "Пожалуйста, попробуйте позже.",
                reply_markup=get_back_to_main_keyboard(),
            )
    else:
        # Robokassa payment flow (still in development)
        await callback.message.answer(
            "💳 <b>Оплата через Robokassa</b>\n\n"
            "Эта функция находится в разработке.\n"
            "Для покупки проверок свяжитесь с поддержкой.\n\n"
            "Или пригласите 10 друзей и получите 1 проверку бесплатно!\n"
            "Используйте /referral для получения реферальной ссылки.",
            reply_markup=get_back_to_main_keyboard(),
        )

