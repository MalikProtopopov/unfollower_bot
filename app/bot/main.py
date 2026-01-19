"""Telegram bot entry point."""

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers.commands import router as commands_router
from app.bot.handlers.callbacks import router as callbacks_router
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

    # Register routers
    dp.include_router(commands_router)
    dp.include_router(callbacks_router)

    logger.info("Starting Mutual Followers Bot...")

    # Start polling
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

