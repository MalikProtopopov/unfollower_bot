"""Telegram bot entry point."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import (
    balance_router,
    check_router,
    info_router,
    payments_router,
    referral_router,
    start_router,
)
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


async def main():
    """Main bot startup function."""
    if not settings.telegram_token:
        logger.error("TELEGRAM_TOKEN not set in environment")
        sys.exit(1)

    # Initialize bot
    bot = Bot(
        token=settings.telegram_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Initialize dispatcher
    dp = Dispatcher()

    # Register routers in order of priority
    # 1. Payments router first for pre_checkout_query and successful_payment handlers
    dp.include_router(payments_router)
    # 2. Check router before start (has FSM states)
    dp.include_router(check_router)
    # 3. Balance router (buy, balance commands)
    dp.include_router(balance_router)
    # 4. Referral router
    dp.include_router(referral_router)
    # 5. Info router (about, last, offer, privacy)
    dp.include_router(info_router)
    # 6. Start router last (has fallback handler for unknown messages)
    dp.include_router(start_router)

    logger.info("Starting Mutual Followers Bot...")

    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
