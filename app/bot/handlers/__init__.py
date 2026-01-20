"""Bot command and callback handlers.

This package contains all Telegram bot handlers split by functionality:
- start.py: /start, /help commands and main menu
- check.py: /check command and check flow FSM
- balance.py: /balance, /buy commands and tariff handling
- referral.py: /referral command
- info.py: /about, /last commands, offer and privacy
- payments.py: Telegram Stars payment handlers
"""

from app.bot.handlers.balance import router as balance_router
from app.bot.handlers.check import router as check_router
from app.bot.handlers.info import router as info_router
from app.bot.handlers.payments import router as payments_router
from app.bot.handlers.referral import router as referral_router
from app.bot.handlers.start import router as start_router

__all__ = [
    "start_router",
    "check_router",
    "balance_router",
    "referral_router",
    "info_router",
    "payments_router",
]
