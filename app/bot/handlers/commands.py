"""Telegram bot command handlers."""

import asyncio
import re

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
            # First, ensure user exists (will be created with balance=1)
            response = await client.get(
                get_api_url(f"/users/{user.id}/balance")
            )
            
            # If user doesn't exist, they'll be created on first check
            # But we need to register the referral
            if referral_code and referral_code.startswith("ref_"):
                # Register referral
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
                        logger.info(f"Referral registered for user {user.id} with code {referral_code}")
    except Exception as e:
        logger.error(f"Error processing referral for user {user.id}: {e}")
    
    await show_welcome_message(message, user)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    user = message.from_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    await show_welcome_message(message, user)


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

    keyboard = InlineKeyboardMarkup(
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
    manager_url = f"https://t.me/issue_resolver?text={prefilled_message.replace(' ', '%20')}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📄 Публичная оферта", callback_data="public_offer")],
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")],
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
                # User doesn't exist yet, create on first check
                await message.answer(
                    "💰 <b>Баланс проверок</b>\n\n"
                    "У вас: <b>1</b> проверка (бесплатная при регистрации)\n\n"
                    "Используйте /check чтобы проверить аккаунт."
                )
                return
            
            response.raise_for_status()
            result = response.json()

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
            await message.answer(
                "🛒 <b>Покупка проверок</b>\n\n"
                "В данный момент нет доступных тарифов."
            )
            return

        text = "🛒 <b>Покупка проверок</b>\n\nВыберите тариф:\n\n"
        
        buttons = []
        for tariff in tariffs:
            name = tariff["name"]
            checks = tariff["checks_count"]
            price_rub = tariff["price_rub"]
            price_stars = tariff.get("price_stars")
            
            text += f"📦 <b>{name}</b>\n"
            text += f"   {checks} проверок — {price_rub}₽"
            if price_stars:
                text += f" или {price_stars}⭐"
            text += "\n\n"
            
            # Button for this tariff
            tariff_id = tariff["tariff_id"]
            buttons.append([
                InlineKeyboardButton(
                    text=f"💳 {name} — {price_rub}₽",
                    callback_data=f"buy_tariff:{tariff_id}:rub"
                )
            ])
            if price_stars:
                buttons.append([
                    InlineKeyboardButton(
                        text=f"⭐ {name} — {price_stars} Stars",
                        callback_data=f"buy_tariff:{tariff_id}:stars"
                    )
                ])

        text += "👥 Или пригласите 10 друзей и получите 1 проверку бесплатно!"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in /buy command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


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
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error in /referral command: {e}")
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")


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
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
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
        await poll_check_status(callback.message, check_id, state)

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


async def poll_check_status(message: Message, check_id: str, state: FSMContext):
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
                await message.edit_text(
                    f"❌ <b>Проверка завершилась с ошибкой</b>\n\n{error_msg}\n\n"
                    "Попробуйте позже: /check"
                )
                await state.clear()
                return

            elif status in ("pending", "processing"):
                # Only update if progress changed to avoid "message not modified" error
                if progress != last_progress:
                    last_progress = progress
                    progress_bar = create_progress_bar(progress)
                    queue_pos = result.get("queue_position")
                    queue_text = f"\nПозиция в очереди: {queue_pos}" if queue_pos else ""
                    try:
                        await message.edit_text(
                            f"⏳ <b>Обработка...</b>\n\n"
                            f"{progress_bar} {progress}%{queue_text}\n\n"
                            f"<i>ID: {check_id[:8]}...</i>"
                        )
                    except Exception:
                        pass  # Ignore "message not modified" errors

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await message.edit_text("❌ Проверка не найдена")
                await state.clear()
                return
        except Exception as e:
            logger.warning(f"Error polling check {check_id}: {e}")

        await asyncio.sleep(poll_interval)

    # Timeout
    await message.edit_text(
        "⏰ <b>Превышено время ожидания</b>\n\n"
        "Проверка заняла слишком много времени.\n"
        "Вы получите уведомление когда она завершится."
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

    await message.edit_text(text)

    # Send file if exists
    if file_path:
        try:
            file = FSInputFile(file_path)
            await message.answer_document(
                file,
                caption="📄 Подробный отчёт в Excel файле"
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
    await callback.message.edit_text(
        "❌ Действие отменено.\n\n"
        "Используйте /check чтобы начать новую проверку."
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
    await cmd_help(callback.message)


# --- Last check callback ---


@router.callback_query(F.data == "last_check")
async def callback_last_check(callback: CallbackQuery):
    """Handle last check button."""
    await callback.answer()
    await cmd_last(callback.message)


# --- Balance callback ---


@router.callback_query(F.data == "balance")
async def callback_balance(callback: CallbackQuery):
    """Handle balance button."""
    await callback.answer()
    await cmd_balance(callback.message)


# --- Buy callback ---


@router.callback_query(F.data == "buy")
async def callback_buy(callback: CallbackQuery):
    """Handle buy button."""
    await callback.answer()
    await show_tariffs(callback.message)


# --- Referral callback ---


@router.callback_query(F.data == "referral")
async def callback_referral(callback: CallbackQuery):
    """Handle referral button."""
    await callback.answer()
    await cmd_referral(callback.message)


# --- Buy tariff callback ---


@router.callback_query(F.data.startswith("buy_tariff:"))
async def callback_buy_tariff(callback: CallbackQuery):
    """Handle tariff purchase button."""
    await callback.answer()
    
    # Parse callback data: buy_tariff:{tariff_id}:{payment_type}
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.message.answer("❌ Ошибка: неверные данные")
        return
    
    tariff_id = parts[1]
    payment_type = parts[2]  # 'rub' or 'stars'
    
    # For now, show a stub message
    # TODO: Implement actual payment flow
    if payment_type == "stars":
        await callback.message.answer(
            "⭐ <b>Оплата через Telegram Stars</b>\n\n"
            "Эта функция находится в разработке.\n"
            "Пожалуйста, попробуйте позже или выберите оплату в рублях."
        )
    else:
        await callback.message.answer(
            "💳 <b>Оплата через Robokassa</b>\n\n"
            "Эта функция находится в разработке.\n"
            "Для покупки проверок свяжитесь с поддержкой.\n\n"
            "Или пригласите 10 друзей и получите 1 проверку бесплатно!\n"
            "Используйте /referral для получения реферальной ссылки."
        )


# --- About callback ---


@router.callback_query(F.data == "about")
async def callback_about(callback: CallbackQuery):
    """Handle about button."""
    await callback.answer()
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
    manager_url = f"https://t.me/issue_resolver?text={prefilled_message.replace(' ', '%20')}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать менеджеру", url=manager_url)],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="about")],
        ]
    )

    await callback.message.edit_text(offer_text, reply_markup=keyboard)


# --- Back to main menu callback ---


@router.callback_query(F.data == "back_to_main")
async def callback_back_to_main(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu button."""
    await callback.answer()
    await state.clear()
    
    user = callback.from_user
    
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

    keyboard = InlineKeyboardMarkup(
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

    await callback.message.edit_text(welcome_text, reply_markup=keyboard)
