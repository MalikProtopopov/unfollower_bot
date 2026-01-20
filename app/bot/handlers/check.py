"""Check flow command handlers with FSM."""

import asyncio

from typing import Optional

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message, User

from app.bot.http_client import (
    APIError,
    APINotFoundError,
    APIPaymentRequiredError,
    api_get,
    api_post,
)
from app.bot.keyboards import (
    get_cancel_result_keyboard,
    get_check_cancel_keyboard,
    get_check_completed_keyboard,
    get_check_confirm_keyboard,
    get_check_error_keyboard,
    get_insufficient_balance_keyboard,
)
from app.bot.utils import create_progress_bar, format_number
from app.utils.logger import logger
from app.utils.validators import normalize_instagram_username

router = Router()


class CheckStates(StatesGroup):
    """FSM states for check flow."""

    waiting_for_username = State()
    processing = State()


# --- /check command ---


@router.message(Command("check"))
async def cmd_check(message: Message, state: FSMContext, user: Optional[User] = None) -> None:
    """Handle /check command - start check flow."""
    await state.clear()
    if user is None:
        user = message.from_user
    user_id = user.id

    # Check balance first
    try:
        result = await api_get(f"/users/{user_id}/balance")
        balance = result.get("checks_balance", 0)

        if balance <= 0:
            await message.answer(
                "❌ <b>Недостаточно проверок</b>\n\n"
                "У вас закончились проверки. Пополните баланс или пригласите друзей.",
                reply_markup=get_insufficient_balance_keyboard(),
            )
            return
    except APINotFoundError:
        # User not found, will be created during check
        pass
    except APIError as e:
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

    await message.answer(text, reply_markup=get_check_cancel_keyboard())
    await state.set_state(CheckStates.waiting_for_username)


# --- Username input handler ---


@router.message(CheckStates.waiting_for_username)
async def process_username(message: Message, state: FSMContext) -> None:
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

    await message.answer(text, reply_markup=get_check_confirm_keyboard())


# --- Start check callback ---


@router.callback_query(F.data == "start_check")
async def callback_start_check(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle start check button from welcome message."""
    await callback.answer()
    # Pass the actual user who clicked, not the message author (which is the bot)
    await cmd_check(callback.message, state, user=callback.from_user)


# --- Confirm check callback ---


@router.callback_query(F.data == "confirm_check")
async def callback_confirm_check(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle check confirmation."""
    await callback.answer()

    data = await state.get_data()
    username = data.get("target_username")

    if not username:
        await callback.message.edit_text(
            "❌ Ошибка: ник не найден. Начните заново: /check",
            reply_markup=get_check_error_keyboard(),
        )
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
        result = await api_post(
            "/check/initiate",
            json={
                "username": username,
                "platform": "instagram",
                "user_id": callback.from_user.id,
            },
        )

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

    except APIPaymentRequiredError:
        await callback.message.edit_text(
            "❌ <b>Недостаточно проверок</b>\n\n"
            "У вас закончились проверки. Пополните баланс или пригласите друзей.",
            reply_markup=get_insufficient_balance_keyboard(),
        )
        await state.clear()

    except APIError as e:
        error_msg = "Ошибка сервера"
        if e.status_code == 400:
            error_msg = "Неверный формат никнейма"
        elif e.status_code == 429:
            error_msg = "Превышен лимит проверок на сегодня"

        await callback.message.edit_text(
            f"❌ {error_msg}\n\nПопробуйте позже: /check",
            reply_markup=get_check_error_keyboard(),
        )
        await state.clear()

    except Exception as e:
        logger.error(f"Error initiating check: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при запуске проверки.\n\n" "Попробуйте позже: /check",
            reply_markup=get_check_error_keyboard(),
        )
        await state.clear()


async def poll_check_status(
    message: Message, check_id: str, username: str, state: FSMContext
) -> None:
    """Poll check status until completion."""
    max_attempts = 120  # 10 minutes with 5 sec intervals
    poll_interval = 5
    last_progress = -1  # Track last progress to avoid "message not modified" error

    for attempt in range(max_attempts):
        try:
            result = await api_get(f"/check/{check_id}")

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
                    f"❌ <b>Проверка завершилась с ошибкой</b>\n\n{error_msg}",
                    reply_markup=get_check_error_keyboard(),
                )
                await state.clear()
                return

            elif status in ("pending", "processing"):
                # Only update if progress changed to avoid "message not modified" error
                if progress != last_progress:
                    last_progress = progress
                    progress_bar = create_progress_bar(progress)
                    queue_pos = result.get("queue_position")
                    queue_text = (
                        f"\n📍 Позиция в очереди: {queue_pos}" if queue_pos and queue_pos > 1 else ""
                    )
                    try:
                        await message.edit_text(
                            f"⏳ <b>Обработка @{username}...</b>\n\n"
                            f"{progress_bar} {progress}%{queue_text}"
                        )
                    except Exception:
                        pass  # Ignore "message not modified" errors

        except APINotFoundError:
            await message.edit_text(
                "❌ Проверка не найдена",
                reply_markup=get_check_error_keyboard(),
            )
            await state.clear()
            return
        except APIError as e:
            logger.warning(f"Error polling check {check_id}: {e}")

        await asyncio.sleep(poll_interval)

    # Timeout
    await message.edit_text(
        "⏰ <b>Превышено время ожидания</b>\n\n"
        "Проверка заняла слишком много времени.\n"
        "Вы получите уведомление когда она завершится.",
        reply_markup=get_check_error_keyboard(),
    )
    await state.clear()


async def handle_check_completed(message: Message, result: dict, state: FSMContext) -> None:
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
• Подписчиков: <b>{format_number(total_followers)}</b>
• Подписок: <b>{format_number(total_subscriptions)}</b>
• Взаимных: <b>{format_number(mutual_count)}</b> ({mutual_percent:.1f}%)
• Не взаимных: <b>{format_number(total_non_mutual)}</b>
"""

    await message.edit_text(text, reply_markup=get_check_completed_keyboard())

    # Send file if exists
    if file_path:
        try:
            file = FSInputFile(file_path)
            await message.answer_document(
                file,
                caption="📄 Подробный отчёт в Excel файле",
                reply_markup=get_check_completed_keyboard(),
            )
        except Exception as e:
            logger.error(f"Error sending file: {e}")
            await message.answer("⚠️ Не удалось отправить файл с отчётом")

    await state.clear()


# --- Cancel callback ---


@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Handle cancel button."""
    await callback.answer("Отменено")
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.",
        reply_markup=get_cancel_result_keyboard(),
    )

