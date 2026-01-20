"""Start and help command handlers."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.http_client import APIError, api_post
from app.bot.keyboards import get_back_button_keyboard, get_main_menu_keyboard
from app.utils.logger import logger

router = Router()


# --- /start command ---


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_referral(message: Message, state: FSMContext) -> None:
    """Handle /start command with referral link."""
    await state.clear()

    user = message.from_user

    # Extract referral code from deep link
    args = message.text.split(maxsplit=1)
    referral_code = args[1] if len(args) > 1 else None

    logger.info(f"User {user.id} ({user.username}) started the bot with referral: {referral_code}")

    # Register user and handle referral
    try:
        result = await api_post(
            "/users/ensure",
            params={
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )
        logger.info(
            f"User {user.id} ensured with balance: {result.get('checks_balance', 0)}, "
            f"referral_code: {result.get('referral_code', 'N/A')}"
        )

        # Register referral if provided
        if referral_code and referral_code.startswith("ref_"):
            logger.info(f"Attempting to register referral: code={referral_code}, user={user.id}")
            try:
                ref_result = await api_post(
                    "/referrals/register",
                    json={
                        "referrer_code": referral_code,
                        "referred_user_id": user.id,
                    },
                )
                if ref_result.get("success"):
                    logger.info(
                        f"✓ Referral registered successfully for user {user.id} with code {referral_code}. "
                        f"Bonus granted: {ref_result.get('bonus_granted_to_referrer', False)}"
                    )
                else:
                    logger.warning(
                        f"Referral registration failed for user {user.id}: "
                        f"{ref_result.get('message', 'Unknown error')}"
                    )
            except APIError as e:
                logger.error(f"Failed to register referral for user {user.id}: {e}")
        elif referral_code:
            logger.warning(
                f"Invalid referral code format for user {user.id}: {referral_code} "
                f"(expected format: ref_123456789)"
            )
    except APIError as e:
        logger.error(f"Error processing referral for user {user.id}: {e}")

    await show_welcome_message(message, user)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Handle /start command."""
    await state.clear()
    user = message.from_user
    logger.info(f"User {user.id} ({user.username}) started the bot")

    # Ensure user exists in database (will be created with proper balance)
    try:
        result = await api_post(
            "/users/ensure",
            params={
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
            },
        )
        logger.info(f"User {user.id} ensured with balance: {result.get('checks_balance', 0)}")
    except APIError as e:
        logger.error(f"Error ensuring user {user.id}: {e}")

    await show_welcome_message(message, user)


async def show_welcome_message(message: Message, user) -> None:
    """Show welcome message with keyboard."""
    welcome_text = f"""
👋 <b>Привет, {user.first_name}!</b>

Я помогу тебе проанализировать взаимные подписки в Instagram.

🔍 <b>Что я умею:</b>
• Показать, кто не подписан на тебя взаимно
• Сгенерировать отчёт в Excel файле
• Сохранить историю проверок

📋 <b>Команды:</b>
/check — начать проверку
/balance — баланс проверок
/buy — купить проверки
/referral — пригласить друзей
/last — последняя проверка
/about — о сервисе

⚠️ <b>Важно:</b> Проверка работает только для публичных аккаунтов.
"""

    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())


async def show_main_menu(message: Message, user=None, edit: bool = False) -> None:
    """Show main menu."""
    if user is None:
        user = message.from_user

    welcome_text = """
👋 <b>Главное меню</b>

Выберите действие:
"""
    keyboard = get_main_menu_keyboard()

    if edit and hasattr(message, "edit_text"):
        await message.edit_text(welcome_text, reply_markup=keyboard)
    else:
        await message.answer(welcome_text, reply_markup=keyboard)


# --- /help command ---


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Handle /help command."""
    help_text = """
📖 <b>Справка по использованию бота</b>

<b>Как проверить подписки:</b>
1. Отправь команду /check
2. Введи Instagram ник или ссылку на профиль
3. Дождись завершения анализа
4. Получи файл с результатами

<b>Что показывает отчёт:</b>
• Список всех ваших подписок
• Кто из них подписан на вас взаимно
• Кто НЕ подписан на вас (не взаимные)

<b>Ограничения:</b>
• Работает только с публичными аккаунтами
• Максимум 10 000 подписок/подписчиков

<b>Команды:</b>
/check — начать проверку
/balance — баланс проверок
/buy — купить проверки
/referral — пригласить друзей и получить бонусы
/last — последняя проверка
/about — о сервисе
/help — эта справка

<b>Возникли проблемы?</b>
Попробуйте позже или проверьте, что аккаунт публичный.
"""

    await message.answer(help_text, reply_markup=get_back_button_keyboard())


# --- Callbacks ---


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery) -> None:
    """Handle help button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_help(callback.message)


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle back to main menu button."""
    await callback.answer()
    await state.clear()
    # Try to edit, fall back to delete+answer if message has no text (e.g., invoice)
    try:
        await show_main_menu(callback.message, callback.from_user, edit=True)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await show_main_menu(callback.message, callback.from_user, edit=False)


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle main menu button."""
    await callback.answer()
    await state.clear()
    # Try to edit, fall back to delete+answer if message has no text (e.g., invoice)
    try:
        await show_main_menu(callback.message, callback.from_user, edit=True)
    except Exception:
        try:
            await callback.message.delete()
        except Exception:
            pass
        await show_main_menu(callback.message, callback.from_user, edit=False)


# --- Fallback handler for unknown messages ---


@router.message()
async def handle_unknown_message(message: Message, state: FSMContext) -> None:
    """Handle any unrecognized message."""
    # Import here to avoid circular import - state names defined in check.py
    from app.bot.handlers.check import CheckStates

    # Check if we're in a state that expects input
    current_state = await state.get_state()
    if current_state == CheckStates.waiting_for_username:
        # This is handled by process_username, skip
        return

    keyboard = get_main_menu_keyboard()
    await message.answer(
        "🤔 Не понял команду.\n\n" "Выберите действие из меню:",
        reply_markup=keyboard,
    )

