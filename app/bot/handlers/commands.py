"""Telegram bot command handlers."""

import asyncio
import re
from urllib.parse import quote

import httpx
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import get_settings
from app.utils.logger import logger
from app.utils.validators import normalize_instagram_username

router = Router()
settings = get_settings()


class CheckStates(StatesGroup):
    """FSM states for check flow."""

    waiting_for_username = State()
    processing = State()


def get_api_url(path: str) -> str:
    """Get full API URL."""
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1{path}"


# --- /start command ---


@router.message(CommandStart(deep_link=True))
async def cmd_start_with_referral(message: Message, state: FSMContext):
    """Handle /start command with referral link."""
    await state.clear()

    user = message.from_user
    
    # Extract referral code from deep link
    args = message.text.split(maxsplit=1)
    referral_code = args[1] if len(args) > 1 else None
    
    logger.info(f"User {user.id} ({user.username}) started the bot with referral: {referral_code}")
    
    # Register user and handle referral
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Ensure user exists (will be created with proper balance)
            response = await client.post(
                get_api_url("/users/ensure"),
                params={
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                }
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"User {user.id} ensured with balance: {result.get('checks_balance', 0)}, "
                    f"referral_code: {result.get('referral_code', 'N/A')}"
                )
            else:
                logger.error(
                    f"Failed to ensure user {user.id}: status={response.status_code}, "
                    f"response={response.text}"
                )
            
            # Register referral if provided
            if referral_code and referral_code.startswith("ref_"):
                logger.info(f"Attempting to register referral: code={referral_code}, user={user.id}")
                ref_response = await client.post(
                    get_api_url("/referrals/register"),
                    json={
                        "referrer_code": referral_code,
                        "referred_user_id": user.id,
                    }
                )
                if ref_response.status_code == 200:
                    ref_result = ref_response.json()
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
                else:
                    logger.error(
                        f"Failed to register referral for user {user.id}: "
                        f"status={ref_response.status_code}, response={ref_response.text}"
                    )
            elif referral_code:
                logger.warning(
                    f"Invalid referral code format for user {user.id}: {referral_code} "
                    f"(expected format: ref_123456789)"
                )
    except Exception as e:
        logger.error(f"Error processing referral for user {user.id}: {e}", exc_info=True)
    
    await show_welcome_message(message, user)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    user = message.from_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    
    # Ensure user exists in database (will be created with proper balance)
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                get_api_url("/users/ensure"),
                params={
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                }
            )
            if response.status_code == 200:
                result = response.json()
                logger.info(f"User {user.id} ensured with balance: {result.get('checks_balance', 0)}")
    except Exception as e:
        logger.error(f"Error ensuring user {user.id}: {e}")
    
    await show_welcome_message(message, user)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get main menu keyboard."""
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


async def show_welcome_message(message: Message, user):
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


async def show_main_menu(message: Message, user=None, edit: bool = False):
    """Show main menu."""
    if user is None:
        user = message.from_user
    
    welcome_text = f"""
👋 <b>Главное меню</b>

Выберите действие:
"""
    keyboard = get_main_menu_keyboard()
    
    if edit and hasattr(message, 'edit_text'):
        await message.edit_text(welcome_text, reply_markup=keyboard)
    else:
        await message.answer(welcome_text, reply_markup=keyboard)


# --- /help command ---


@router.message(Command("help"))
async def cmd_help(message: Message):
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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Главное меню", callback_data="back_to_main")],
        ]
    )

    await message.answer(help_text, reply_markup=keyboard)


# --- /about command ---


@router.message(Command("about"))
async def cmd_about(message: Message):
    """Handle /about command - show info about the service."""
    await show_about(message)


async def show_about(message: Message):
    """Show about page with inline buttons."""
    about_text = """
ℹ️ <b>О сервисе</b>

<b>CheckFollowers Bot</b> — это сервис для анализа взаимных подписок в Instagram.

🔍 <b>Что мы делаем:</b>
Анализируем ваши подписки и подписчиков, чтобы показать, кто не подписан на вас взаимно. Формируем удобный Excel-отчёт со всеми данными.

⚡️ <b>Преимущества:</b>
• Быстрый анализ аккаунтов
• Подробные отчёты в Excel
• Автоматические уведомления
• Реферальная программа

📊 Работаем с аккаунтами до 10 000 подписок/подписчиков.

По всем вопросам обращайтесь к менеджеру 👇
"""

    # Pre-filled message for manager
    prefilled_message = "Здравствуйте! Пишу по поводу бота CheckFollowers для анализа подписок Instagram."
    manager_url = f"https://t.me/issue_resolver?text={quote(prefilled_message)}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Публичная оферта", callback_data="public_offer")],
            [InlineKeyboardButton(text="🔒 Политика конфиденциальности", callback_data="privacy_policy")],
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )

    await message.answer(about_text, reply_markup=keyboard)


# --- /balance command ---


@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Handle /balance command - show user's check balance."""
    user_id = message.from_user.id

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(get_api_url(f"/users/{user_id}/balance"))
            
            if response.status_code == 404:
                # User doesn't exist yet
                await message.answer(
                    "💰 <b>Баланс проверок</b>\n\n"
                    "У вас: <b>0</b> проверок\n\n"
                    "Для проверки нужно пополнить баланс или пригласить друзей.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
                            [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                        ]
                    )
                )
                return
            
            response.raise_for_status()
            result = response.json()
            
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

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
                [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in /balance command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


# --- /buy command ---


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    """Handle /buy command - show available tariffs."""
    await show_tariffs(message)


async def show_tariffs(message: Message):
    """Show available tariffs for purchase."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(get_api_url("/tariffs"))
            response.raise_for_status()
            result = response.json()

        tariffs = result.get("tariffs", [])
        
        if not tariffs:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                ]
            )
            await message.answer(
                "🛒 <b>Покупка проверок</b>\n\n"
                "В данный момент нет доступных тарифов.",
                reply_markup=keyboard
            )
            return

        text = "🛒 <b>Покупка проверок</b>\n\nВыберите тариф:\n\n"
        
        # Stars buttons only (RUB temporarily disabled)
        stars_buttons = []
        
        for tariff in tariffs:
            name = tariff["name"]
            checks = tariff["checks_count"]
            price_stars = tariff.get("price_stars")
            
            if price_stars:
                text += f"📦 <b>{name}</b>\n"
                text += f"   {checks} проверок — {price_stars}⭐\n\n"
                
                tariff_id = tariff["tariff_id"]
                stars_buttons.append([
                    InlineKeyboardButton(
                        text=f"⭐ {name} — {price_stars} Stars",
                        callback_data=f"buy_tariff:{tariff_id}:stars"
                    )
                ])

        text += "👥 Или пригласите 10 друзей и получите 1 проверку бесплатно!"
        
        # Combine buttons: Stars section, then navigation
        all_buttons = []
        
        if stars_buttons:
            all_buttons.extend(stars_buttons)
        
        # Navigation buttons
        all_buttons.append([
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=all_buttons)
        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in /buy command: {e}")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]
        )
        await message.answer("❌ Произошла ошибка. Попробуйте позже.", reply_markup=keyboard)


# --- /referral command ---


@router.message(Command("referral"))
async def cmd_referral(message: Message):
    """Handle /referral command - show referral program info."""
    user_id = message.from_user.id

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                get_api_url("/referrals/stats"),
                params={"user_id": user_id}
            )
            
            if response.status_code == 404:
                # User doesn't exist yet
                bot_username = settings.bot_username or "your_bot"
                referral_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
                
                await message.answer(
                    f"👥 <b>Реферальная программа</b>\n\n"
                    f"Приглашайте друзей и получайте бонусы!\n\n"
                    f"🎁 <b>10 друзей = 1 бесплатная проверка</b>\n\n"
                    f"📎 Ваша ссылка:\n<code>{referral_link}</code>\n\n"
                    f"Приглашено: <b>0</b>\n"
                    f"До бонуса: <b>10</b> друзей"
                )
                return
            
            response.raise_for_status()
            stats = response.json()
            
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
        progress_bar = "🟢" * progress + "⚪" * (10 - progress)

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

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text="📤 Поделиться ссылкой",
                    switch_inline_query=f"Проверь свои подписки в Instagram! {referral_link}"
                )],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in /referral command: {e}")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]
        )
        await message.answer("❌ Произошла ошибка. Попробуйте позже.", reply_markup=keyboard)


# --- /last command ---


@router.message(Command("last"))
async def cmd_last(message: Message):
    """Handle /last command - get last check result."""
    user_id = message.from_user.id

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get user's check history
            response = await client.get(
                get_api_url("/checks"),
                params={"user_id": user_id, "limit": 1},
            )
            response.raise_for_status()
            result = response.json()

        if not result["checks"]:
            await message.answer(
                "📭 <b>У вас пока нет проверок</b>\n\n"
                "Используйте /check чтобы начать первую проверку."
            )
            return

        last_check = result["checks"][0]
        check_id = last_check["check_id"]
        status = last_check["status"]
        username = last_check["target_username"]

        if status == "completed":
            # Get full check details
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(get_api_url(f"/check/{check_id}"))
                response.raise_for_status()
                check_data = response.json()

            total_followers = check_data.get("total_followers", 0)
            total_following = check_data.get("total_subscriptions", 0)
            total_non_mutual = check_data.get("total_non_mutual", 0)
            file_path = check_data.get("file_path")

            text = f"""
✅ <b>Последняя проверка: @{username}</b>

📊 <b>Результаты:</b>
• Подписчиков: <b>{total_followers:,}</b>
• Подписок: <b>{total_following:,}</b>
• Не взаимных: <b>{total_non_mutual:,}</b>
"""
            await message.answer(text)

            # Send file if exists
            if file_path:
                try:
                    file = FSInputFile(file_path)
                    await message.answer_document(
                        file,
                        caption="📄 Отчёт в Excel"
                    )
                except Exception as e:
                    logger.error(f"Error sending file: {e}")
                    await message.answer("⚠️ Не удалось отправить файл")

        elif status == "processing":
            await message.answer(
                f"⏳ <b>Проверка @{username} ещё выполняется...</b>\n\n"
                "Подождите завершения или используйте /check для новой проверки."
            )

        elif status == "failed":
            error_msg = last_check.get("error_message", "Неизвестная ошибка")
            await message.answer(
                f"❌ <b>Последняя проверка @{username} завершилась с ошибкой</b>\n\n"
                f"{error_msg}\n\n"
                "Используйте /check для новой проверки."
            )

        else:
            await message.answer(
                f"⏳ <b>Проверка @{username} в очереди</b>\n\n"
                "Подождите завершения."
            )

    except Exception as e:
        logger.error(f"Error in /last command: {e}")
        await message.answer(
            "❌ Произошла ошибка при получении данных.\n\n"
            "Попробуйте позже."
        )


# --- /check command ---


@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext):
    """Handle /check command - start check flow."""
    await state.clear()
    user_id = message.from_user.id

    # Check balance first
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(get_api_url(f"/users/{user_id}/balance"))
            
            if response.status_code == 200:
                result = response.json()
                balance = result.get("checks_balance", 0)
                
                if balance <= 0:
                    await message.answer(
                        "❌ <b>Недостаточно проверок</b>\n\n"
                        "У вас закончились проверки. Пополните баланс или пригласите друзей.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[
                                [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
                                [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
                                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                            ]
                        )
                    )
                    return
    except Exception as e:
        logger.warning(f"Could not check balance for user {user_id}: {e}")
        # Continue anyway - API will check balance

    text = """
🔍 <b>Проверка взаимных подписок</b>

Отправь мне Instagram ник или ссылку на профиль.

<b>Примеры:</b>
• <code>username</code>
• <code>@username</code>
• <code>https://instagram.com/username</code>
"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )

    await message.answer(text, reply_markup=keyboard)
    await state.set_state(CheckStates.waiting_for_username)


# --- Username input handler ---


@router.message(CheckStates.waiting_for_username)
async def process_username(message: Message, state: FSMContext):
    """Process Instagram username input."""
    user_input = message.text.strip()

    # Validate and normalize username
    username = normalize_instagram_username(user_input)

    if not username:
        await message.answer(
            "❌ Неверный формат никнейма.\n\n"
            "Отправь Instagram ник (например: <code>username</code>) "
            "или ссылку на профиль."
        )
        return

    await state.update_data(target_username=username)

    # Confirm before starting
    text = f"""
📋 <b>Подтверждение</b>

Проверить аккаунт: <b>@{username}</b>

Это может занять несколько минут в зависимости от количества подписок.
"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Начать", callback_data="confirm_check"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
            ]
        ]
    )

    await message.answer(text, reply_markup=keyboard)


# --- Confirm check callback ---


@router.callback_query(F.data == "confirm_check")
async def callback_confirm_check(callback: CallbackQuery, state: FSMContext):
    """Handle check confirmation."""
    await callback.answer()

    data = await state.get_data()
    username = data.get("target_username")

    if not username:
        await callback.message.edit_text("❌ Ошибка: ник не найден. Начните заново: /check")
        await state.clear()
        return

    await state.set_state(CheckStates.processing)

    # Update message
    await callback.message.edit_text(
        f"⏳ <b>Запускаю проверку для @{username}...</b>\n\n"
        "Это может занять некоторое время."
    )

    # Initiate check via API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                get_api_url("/check/initiate"),
                json={
                    "username": username,
                    "platform": "instagram",
                    "user_id": callback.from_user.id,
                },
            )
            
            if response.status_code == 402:
                # Payment required
                await callback.message.edit_text(
                    "❌ <b>Недостаточно проверок</b>\n\n"
                    "У вас закончились проверки. Пополните баланс или пригласите друзей.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🛒 Купить проверки", callback_data="buy")],
                            [InlineKeyboardButton(text="👥 Пригласить друзей", callback_data="referral")],
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                        ]
                    )
                )
                await state.clear()
                return
            
            response.raise_for_status()
            result = response.json()

        check_id = result["check_id"]
        queue_position = result.get("queue_position", 1)
        await state.update_data(check_id=check_id)

        logger.info(f"Check {check_id} initiated for @{username} by user {callback.from_user.id}")

        # Show queue position if not first
        if queue_position > 1:
            await callback.message.edit_text(
                f"⏳ <b>Проверка @{username} добавлена в очередь</b>\n\n"
                f"Позиция в очереди: <b>{queue_position}</b>\n\n"
                f"Вы получите уведомление когда проверка завершится.\n"
                f"Можете закрыть бота — результат придёт автоматически."
            )
        else:
            await callback.message.edit_text(
                f"⏳ <b>Проверка @{username} началась...</b>\n\n"
                f"Вы получите уведомление когда проверка завершится.\n"
                f"Можете закрыть бота — результат придёт автоматически."
            )

        # Start polling (optional, since we have push notifications)
        await poll_check_status(callback.message, check_id, username, state)

    except httpx.HTTPStatusError as e:
        error_msg = "Ошибка сервера"
        if e.response.status_code == 400:
            error_msg = "Неверный формат никнейма"
        elif e.response.status_code == 429:
            error_msg = "Превышен лимит проверок на сегодня"

        await callback.message.edit_text(f"❌ {error_msg}\n\nПопробуйте позже: /check")
        await state.clear()

    except Exception as e:
        logger.error(f"Error initiating check: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при запуске проверки.\n\n"
            "Попробуйте позже: /check"
        )
        await state.clear()


async def poll_check_status(message: Message, check_id: str, username: str, state: FSMContext):
    """Poll check status until completion."""
    max_attempts = 120  # 10 minutes with 5 sec intervals
    poll_interval = 5
    last_progress = -1  # Track last progress to avoid "message not modified" error

    for attempt in range(max_attempts):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(get_api_url(f"/check/{check_id}"))
                response.raise_for_status()
                result = response.json()

            status = result["status"]
            progress = result.get("progress", 0)

            if status == "completed":
                # Success!
                await handle_check_completed(message, result, state)
                return

            elif status == "failed":
                # Error
                error_msg = result.get("error_message", "Неизвестная ошибка")
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="start_check")],
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                    ]
                )
                await message.edit_text(
                    f"❌ <b>Проверка завершилась с ошибкой</b>\n\n{error_msg}",
                    reply_markup=keyboard
                )
                await state.clear()
                return

            elif status in ("pending", "processing"):
                # Only update if progress changed to avoid "message not modified" error
                if progress != last_progress:
                    last_progress = progress
                    progress_bar = create_progress_bar(progress)
                    queue_pos = result.get("queue_position")
                    queue_text = f"\n📍 Позиция в очереди: {queue_pos}" if queue_pos and queue_pos > 1 else ""
                    try:
                        await message.edit_text(
                            f"⏳ <b>Обработка @{username}...</b>\n\n"
                            f"{progress_bar} {progress}%{queue_text}"
                        )
                    except Exception:
                        pass  # Ignore "message not modified" errors

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                keyboard = InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                    ]
                )
                await message.edit_text("❌ Проверка не найдена", reply_markup=keyboard)
                await state.clear()
                return
        except Exception as e:
            logger.warning(f"Error polling check {check_id}: {e}")

        await asyncio.sleep(poll_interval)

    # Timeout
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )
    await message.edit_text(
        "⏰ <b>Превышено время ожидания</b>\n\n"
        "Проверка заняла слишком много времени.\n"
        "Вы получите уведомление когда она завершится.",
        reply_markup=keyboard
    )
    await state.clear()


async def handle_check_completed(message: Message, result: dict, state: FSMContext):
    """Handle completed check - send results."""
    total_subscriptions = result.get("total_subscriptions", 0)
    total_followers = result.get("total_followers", 0)
    total_non_mutual = result.get("total_non_mutual", 0)
    file_path = result.get("file_path")

    # Calculate stats
    mutual_count = total_subscriptions - total_non_mutual
    mutual_percent = (mutual_count / total_subscriptions * 100) if total_subscriptions else 0

    text = f"""
✅ <b>Проверка завершена!</b>

📊 <b>Статистика:</b>
• Подписчиков: <b>{total_followers:,}</b>
• Подписок: <b>{total_subscriptions:,}</b>
• Взаимных: <b>{mutual_count:,}</b> ({mutual_percent:.1f}%)
• Не взаимных: <b>{total_non_mutual:,}</b>
"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Новая проверка", callback_data="start_check")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )

    await message.edit_text(text, reply_markup=keyboard)

    # Send file if exists
    if file_path:
        try:
            file = FSInputFile(file_path)
            file_keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 Новая проверка", callback_data="start_check")],
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                ]
            )
            await message.answer_document(
                file,
                caption="📄 Подробный отчёт в Excel файле",
                reply_markup=file_keyboard
            )
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await message.answer("⚠️ Не удалось отправить файл с отчётом")

    await state.clear()


def create_progress_bar(progress: int, length: int = 10) -> str:
    """Create text progress bar."""
    filled = int(progress / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


# --- Cancel callback ---


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle cancel button."""
    await callback.answer("Отменено")
    await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Начать проверку", callback_data="start_check")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )
    await callback.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=keyboard
    )


# --- Start check callback ---


@router.callback_query(F.data == "start_check")
async def callback_start_check(callback: CallbackQuery, state: FSMContext):
    """Handle start check button from welcome message."""
    await callback.answer()
    await cmd_check(callback.message, state)


# --- Help callback ---


@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Handle help button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_help(callback.message)


# --- Last check callback ---


@router.callback_query(F.data == "last_check")
async def callback_last_check(callback: CallbackQuery):
    """Handle last check button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_last(callback.message)


# --- Balance callback ---


@router.callback_query(F.data == "balance")
async def callback_balance(callback: CallbackQuery):
    """Handle balance button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_balance(callback.message)


# --- Buy callback ---


@router.callback_query(F.data == "buy")
async def callback_buy(callback: CallbackQuery):
    """Handle buy button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_tariffs(callback.message)


# --- Referral callback ---


@router.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery):
    """Handle referral button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await cmd_referral(callback.message)


# --- Buy tariff callback ---


@router.callback_query(F.data.startswith("buy_tariff:"))
async def callback_buy_tariff(callback: CallbackQuery):
    """Handle tariff purchase button."""
    await callback.answer()
    
    # Parse callback data: buy_tariff:{tariff_id}:{payment_type}
    parts = callback.data.split(":")
    if len(parts) != 3:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]
        )
        await callback.message.answer("❌ Ошибка: неверные данные", reply_markup=keyboard)
        return
    
    tariff_id = parts[1]
    payment_type = parts[2]  # 'rub' or 'stars'
    user_id = callback.from_user.id
    
    if payment_type == "stars":
        # Create payment and send invoice for Telegram Stars
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create payment via API
                response = await client.post(
                    get_api_url("/payments/telegram-stars/create"),
                    json={
                        "user_id": user_id,
                        "tariff_id": tariff_id,
                    },
                )
                
                if response.status_code == 200:
                    result = response.json()
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
                        f"Stars invoice sent for user {user_id}, "
                        f"tariff={tariff_name}, price={price_stars}"
                    )
                    
                elif response.status_code == 404:
                    error_detail = response.json().get("detail", "Тариф не найден")
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                        ]
                    )
                    await callback.message.answer(f"❌ {error_detail}", reply_markup=keyboard)
                    
                elif response.status_code == 400:
                    error_detail = response.json().get("detail", "Тариф недоступен")
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                        ]
                    )
                    await callback.message.answer(f"❌ {error_detail}", reply_markup=keyboard)
                    
                else:
                    logger.error(
                        f"Error creating Stars payment: status={response.status_code}, "
                        f"body={response.text}"
                    )
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                        ]
                    )
                    await callback.message.answer(
                        "❌ Не удалось создать платёж.\n"
                        "Пожалуйста, попробуйте позже.",
                        reply_markup=keyboard
                    )
                    
        except httpx.TimeoutException:
            logger.error(f"Timeout creating Stars payment for user {user_id}")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                ]
            )
            await callback.message.answer(
                "⏳ Превышено время ожидания.\n"
                "Пожалуйста, попробуйте позже.",
                reply_markup=keyboard
            )
        except Exception as e:
            logger.error(f"Error creating Stars payment for user {user_id}: {e}")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
                ]
            )
            await callback.message.answer(
                "❌ Произошла ошибка.\n"
                "Пожалуйста, попробуйте позже.",
                reply_markup=keyboard
            )
    else:
        # Robokassa payment flow (still in development)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
            ]
        )
        await callback.message.answer(
            "💳 <b>Оплата через Robokassa</b>\n\n"
            "Эта функция находится в разработке.\n"
            "Для покупки проверок свяжитесь с поддержкой.\n\n"
            "Или пригласите 10 друзей и получите 1 проверку бесплатно!\n"
            "Используйте /referral для получения реферальной ссылки.",
            reply_markup=keyboard
        )


# --- About callback ---


@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    """Handle about button."""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await show_about(callback.message)


# --- Public offer callback ---


@router.callback_query(F.data == "public_offer")
async def callback_public_offer(callback: CallbackQuery):
    """Handle public offer button - show offer text."""
    await callback.answer()
    
    offer_text = """
📄 <b>Публичная оферта</b>

<b>1. Общие положения</b>
Настоящий документ является публичной офертой сервиса CheckFollowers Bot для анализа взаимных подписок в Instagram.

<b>2. Описание услуги</b>
Сервис предоставляет возможность анализа подписок и подписчиков аккаунтов Instagram для выявления невзаимных подписок.

<b>3. Стоимость услуг</b>
Стоимость услуг определяется действующими тарифами, доступными в разделе /buy.

<b>4. Порядок оказания услуг</b>
• Услуга предоставляется после списания проверки с баланса
• Результат формируется в виде Excel-отчёта
• Время обработки зависит от размера аккаунта

<b>5. Ограничения</b>
• Сервис работает только с публичными аккаунтами
• Максимальный размер аккаунта: 10 000 подписок/подписчиков

<b>6. Ответственность</b>
Сервис не несёт ответственности за действия Instagram и изменения в их API.

<b>7. Контакты</b>
По всем вопросам: @issue_resolver
"""

    # Pre-filled message for manager
    prefilled_message = "Здравствуйте! Пишу по поводу бота CheckFollowers для анализа подписок Instagram."
    manager_url = f"https://t.me/issue_resolver?text={quote(prefilled_message)}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="about")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )

    await callback.message.edit_text(offer_text, reply_markup=keyboard)


# --- Privacy Policy callback ---


@router.callback_query(F.data == "privacy_policy")
async def callback_privacy_policy(callback: CallbackQuery):
    """Handle privacy policy button - show privacy policy text."""
    await callback.answer()
    
    privacy_text = """
🔒 <b>Политика конфиденциальности</b>

<b>1. Какие данные мы собираем</b>
Для оказания услуг сервис собирает и обрабатывает следующие данные:
• Telegram ID пользователя
• Telegram username (имя пользователя)
• Имя и фамилия в Telegram (если указаны)
• Номер телефона (если предоставлен через Telegram)

<b>2. Цель сбора данных</b>
Данные используются исключительно для:
• Идентификации пользователя в системе
• Начисления и учёта баланса проверок
• Отправки уведомлений о результатах проверок
• Связи с пользователем по вопросам сервиса
• Работы реферальной программы

<b>3. Хранение данных</b>
• Данные хранятся на защищённых серверах
• Доступ к данным имеют только администраторы сервиса
• Данные не передаются третьим лицам

<b>4. Удаление данных</b>
Вы можете запросить удаление своих данных, написав менеджеру @issue_resolver

<b>5. Согласие</b>
Используя сервис, вы соглашаетесь с данной политикой конфиденциальности.

<b>6. Контакты</b>
По вопросам обработки данных: @issue_resolver
"""

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="about")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
        ]
    )

    await callback.message.edit_text(privacy_text, reply_markup=keyboard)


# --- Back to main menu callback ---


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu button."""
    await callback.answer()
    await state.clear()
    await show_main_menu(callback.message, callback.from_user, edit=True)


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Handle main menu button."""
    await callback.answer()
    await state.clear()
    await show_main_menu(callback.message, callback.from_user, edit=True)


# --- Fallback handler for unknown messages ---


@router.message()
async def handle_unknown_message(message: Message, state: FSMContext):
    """Handle any unrecognized message."""
    # Check if we're in a state that expects input
    current_state = await state.get_state()
    if current_state == CheckStates.waiting_for_username:
        # This is handled by process_username, skip
        return
    
    keyboard = get_main_menu_keyboard()
    await message.answer(
        "🤔 Не понял команду.\n\n"
        "Выберите действие из меню:",
        reply_markup=keyboard
    )
