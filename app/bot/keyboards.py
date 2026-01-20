"""Keyboard builders for the Telegram bot."""

from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.utils import get_bot_username, get_manager_username


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get main menu keyboard with primary actions.
    
    Returns:
        InlineKeyboardMarkup with main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Начать проверку", callback_data="start_check")],
            [
                InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
                InlineKeyboardButton(text="🛒 Купить", callback_data="buy"),
            ],
            [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
            [
                InlineKeyboardButton(text="ℹ️ О сервисе", callback_data="about"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
            ],
        ]
    )


def get_back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with just the main menu button.
    
    Returns:
        InlineKeyboardMarkup with main menu button
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_back_button_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard with back to main menu button.
    
    Returns:
        InlineKeyboardMarkup with back button
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")],
        ]
    )


def get_buy_balance_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for balance screen with buy and referral options.
    
    Returns:
        InlineKeyboardMarkup with buy and referral buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
            [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_insufficient_balance_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard shown when user has insufficient balance.
    
    Returns:
        InlineKeyboardMarkup with buy and referral options
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
            [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_check_cancel_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for check flow with cancel option.
    
    Returns:
        InlineKeyboardMarkup with cancel and main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_check_confirm_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for check confirmation.
    
    Returns:
        InlineKeyboardMarkup with confirm and cancel buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Начать", callback_data="confirm_check"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            ]
        ]
    )


def get_check_completed_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard shown after check completion.
    
    Returns:
        InlineKeyboardMarkup with new check and main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Новая проверка", callback_data="start_check")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_check_error_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard shown after check error.
    
    Returns:
        InlineKeyboardMarkup with retry and main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="start_check")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_cancel_result_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard shown after cancel action.
    
    Returns:
        InlineKeyboardMarkup with start check and main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Начать проверку", callback_data="start_check")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_referral_keyboard(referral_link: str) -> InlineKeyboardMarkup:
    """Get keyboard for referral screen.
    
    Args:
        referral_link: User's referral link
    
    Returns:
        InlineKeyboardMarkup with share button and main menu
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Поделиться ссылкой",
                    switch_inline_query=f"Проверь свои подписки в Instagram! {referral_link}",
                )
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_about_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for about screen.
    
    Returns:
        InlineKeyboardMarkup with offer, privacy, manager contact and main menu
    """
    # Pre-filled message for manager
    prefilled_message = "Здравствуйте! Пишу по поводу бота CheckFollowers для анализа подписок Instagram."
    manager_url = f"https://t.me/{get_manager_username()}?text={quote(prefilled_message)}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Публичная оферта", callback_data="public_offer")],
            [
                InlineKeyboardButton(
                    text="🔒 Политика конфиденциальности", callback_data="privacy_policy"
                )
            ],
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_offer_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for public offer screen.
    
    Returns:
        InlineKeyboardMarkup with manager contact, back and main menu buttons
    """
    prefilled_message = "Здравствуйте! Пишу по поводу бота CheckFollowers для анализа подписок Instagram."
    manager_url = f"https://t.me/{get_manager_username()}?text={quote(prefilled_message)}"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="about")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def get_privacy_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for privacy policy screen.
    
    Returns:
        InlineKeyboardMarkup with back and main menu buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="about")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )


def build_tariffs_keyboard(tariffs: list[dict]) -> InlineKeyboardMarkup:
    """Build keyboard with tariff buttons for Stars payment.
    
    Args:
        tariffs: List of tariff dictionaries with tariff_id, name, price_stars
        
    Returns:
        InlineKeyboardMarkup with tariff buttons and navigation
    """
    buttons = []

    for tariff in tariffs:
        name = tariff["name"]
        price_stars = tariff.get("price_stars")
        tariff_id = tariff["tariff_id"]

        if price_stars:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"⭐ {name} — {price_stars} Stars",
                        callback_data=f"buy_tariff:{tariff_id}:stars",
                    )
                ]
            )

    # Add navigation button
    buttons.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

