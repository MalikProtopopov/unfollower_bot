"""Referral command handlers."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.http_client import APIError, APINotFoundError, api_get
from app.bot.keyboards import get_back_to_main_keyboard, get_referral_keyboard
from app.bot.utils import create_referral_progress_bar, get_bot_username
from app.utils.logger import logger

router = Router()


# --- /referral command ---


@router.message(Command("referral"))
async def cmd_referral(message: Message) -> None:
    """Handle /referral command - show referral program info."""
    user_id = message.from_user.id

    try:
        stats = await api_get("/referrals/stats", params={"user_id": user_id})

        logger.info(
            f"Referral stats API response for user {user_id}: "
            f"total_referrals={stats.get('total_referrals')}, "
            f"referrals_for_bonus={stats.get('referrals_for_bonus')}, "
            f"bonus_progress={stats.get('bonus_progress')}, "
            f"total_bonuses_earned={stats.get('total_bonuses_earned')}, "
            f"full_response={stats}"
        )

        referral_link = stats.get("referral_link", "")
        total = stats.get("total_referrals", 0)
        for_bonus = stats.get("referrals_for_bonus", 10)
        progress = stats.get("bonus_progress", 0)
        bonuses_earned = stats.get("total_bonuses_earned", 0)

        # Progress bar
        progress_bar = create_referral_progress_bar(progress)

        text = f"""
👥 <b>Реферальная программа</b>

Приглашайте друзей и получайте бонусы!

🎁 <b>10 друзей = 1 бесплатная проверка</b>

📎 Ваша ссылка:
<code>{referral_link}</code>

📊 <b>Статистика:</b>
• Приглашено: <b>{total}</b>
• До бонуса: <b>{for_bonus}</b> друзей
• Получено бонусов: <b>{bonuses_earned}</b>

{progress_bar} {progress}/10
"""

        await message.answer(text, reply_markup=get_referral_keyboard(referral_link))

    except APINotFoundError:
        # User doesn't exist yet
        bot_username = get_bot_username()
        referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"

        await message.answer(
            f"👥 <b>Реферальная программа</b>\n\n"
            f"Приглашайте друзей и получайте бонусы!\n\n"
            f"🎁 <b>10 друзей = 1 бесплатная проверка</b>\n\n"
            f"📎 Ваша ссылка:\n<code>{referral_link}</code>\n\n"
            f"Приглашено: <b>0</b>\n"
            f"До бонуса: <b>10</b> друзей",
            reply_markup=get_referral_keyboard(referral_link),
        )

    except APIError as e:
        logger.error(f"Error in /referral command: {e}")
        await message.answer(
            "❌ Произошла ошибка. Попробуйте позже.",
            reply_markup=get_back_to_main_keyboard(),
        )


# --- Callback ---


@router.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery) -> None:
    """Handle referral button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_referral(callback.message)

