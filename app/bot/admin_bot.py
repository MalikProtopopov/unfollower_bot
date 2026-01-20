"""Admin Telegram bot entry point.

This is a separate bot for admin commands that runs on ADMIN_BOT_TOKEN.
It handles admin-only commands like session management, stats, etc.
"""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers.admin import router as admin_router
from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


async def main():
    """Main admin bot startup function."""
    admin_token = settings.effective_admin_bot_token
    
    if not admin_token:
        logger.error("ADMIN_BOT_TOKEN (or TELEGRAM_TOKEN) not set in environment")
        sys.exit(1)

    # Initialize admin bot
    bot = Bot(
        token=admin_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # Initialize dispatcher
    dp = Dispatcher()

    # Register only admin router
    dp.include_router(admin_router)

    logger.info("Starting Admin Bot...")
    logger.info(f"Admin user IDs: {settings.admin_ids}")

    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

