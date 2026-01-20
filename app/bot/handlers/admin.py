"""Admin command handlers for bot management.

Provides commands for admin users to manage Instagram sessions,
view statistics, and perform administrative tasks.
"""

from urllib.parse import unquote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.services.session_service import (
    get_all_sessions,
    get_session_info,
    save_session_id,
    validate_session_id,
)
from app.utils.logger import logger

router = Router()
settings = get_settings()


def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return settings.is_admin(user_id)


# --- /admin_set_session command ---


@router.message(Command("admin_set_session"))
async def cmd_admin_set_session(message: Message) -> None:
    """Handle /admin_set_session <session_id> command.
    
    Validates and saves a new Instagram session ID.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    # Extract session_id from command
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/admin_set_session YOUR_SESSION_ID</code>\n\n"
            "Получите session_id из cookie браузера после входа в Instagram.",
            parse_mode="HTML"
        )
        return
    
    # Decode URL-encoded session ID (handles %3A -> :, etc.)
    raw_session_id = parts[1].strip()
    new_session_id = unquote(raw_session_id)
    
    # Log if decoding changed the value
    if raw_session_id != new_session_id:
        logger.info(f"Decoded URL-encoded session ID (length: {len(new_session_id)})")
    
    # Mask for display
    masked = new_session_id[:8] + "..." + new_session_id[-4:] \
        if len(new_session_id) > 12 else "***"
    
    await message.answer(
        f"⏳ Проверяю токен <code>{masked}</code>...",
        parse_mode="HTML"
    )
    
    # Validate the session
    is_valid, validation_message = await validate_session_id(new_session_id)
    
    if not is_valid:
        await message.answer(
            f"❌ <b>Токен невалиден!</b>\n\n"
            f"Причина: {validation_message}\n\n"
            f"Токен НЕ сохранён. Попробуйте получить новый session_id.",
            parse_mode="HTML"
        )
        logger.warning(f"Admin {user_id} tried to set invalid session: {validation_message}")
        return
    
    # Save to database
    try:
        session = await save_session_id(
            session_id=new_session_id,
            notes=f"Set by admin {user_id} via Telegram"
        )
        
        # Show validation status in message
        validation_emoji = "✅" if "valid" in validation_message.lower() else "⚠️"
        
        await message.answer(
            f"{validation_emoji} <b>Токен установлен и сохранён!</b>\n\n"
            f"🔑 Session: <code>{masked}</code>\n"
            f"🆔 ID в базе: {session.id}\n"
            f"📅 Создан: {session.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"🔍 Проверка: {validation_message}\n\n"
            f"Токен будет использоваться для всех проверок.",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} set new Instagram session (DB ID: {session.id}, validation: {validation_message})")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при сохранении:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to save session: {e}")


# --- /admin_check_session command ---


@router.message(Command("admin_check_session"))
async def cmd_admin_check_session(message: Message) -> None:
    """Handle /admin_check_session command.
    
    Shows current session status and validates it.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    await message.answer("⏳ Проверяю текущую сессию...")
    
    # Get session info from database
    session_info = await get_session_info()
    
    if not session_info:
        # Check if there's an env fallback
        env_session = settings.instagram_session_id
        if env_session:
            masked = env_session[:8] + "..." + env_session[-4:] \
                if len(env_session) > 12 else "***"
            await message.answer(
                f"⚠️ <b>Нет сессии в базе данных</b>\n\n"
                f"Используется fallback из .env:\n"
                f"<code>{masked}</code>\n\n"
                f"Рекомендуется установить сессию через:\n"
                f"<code>/admin_set_session YOUR_TOKEN</code>",
                parse_mode="HTML"
            )
        else:
            await message.answer(
                "❌ <b>Сессия не настроена!</b>\n\n"
                "Нет токена ни в базе, ни в .env.\n"
                "Используйте: <code>/admin_set_session YOUR_TOKEN</code>",
                parse_mode="HTML"
            )
        return
    
    # Validate current session
    # Get full session_id for validation
    from app.services.session_service import get_active_session_id
    active_session = await get_active_session_id()
    
    validation_status = "⏳ Проверяется..."
    if active_session:
        is_valid, validation_msg = await validate_session_id(active_session)
        if is_valid:
            validation_status = "✅ Действителен"
        else:
            validation_status = f"❌ Недействителен: {validation_msg}"
    
    # Format response
    status_emoji = "✅" if session_info["is_active"] and session_info["is_valid"] else "⚠️"
    
    text = f"""
{status_emoji} <b>Текущая Instagram сессия</b>

🔑 <b>Token:</b> <code>{session_info['session_id_masked']}</code>
🆔 <b>ID:</b> {session_info['id']}
📊 <b>Статус в БД:</b> {'Активна' if session_info['is_active'] else 'Неактивна'}
✅ <b>Валидна:</b> {'Да' if session_info['is_valid'] else 'Нет'}

🔍 <b>Проверка API:</b> {validation_status}

📅 <b>Создана:</b> {session_info['created_at'][:19] if session_info['created_at'] else 'N/A'}
🕐 <b>Использована:</b> {session_info['last_used_at'][:19] if session_info['last_used_at'] else 'Никогда'}
✔️ <b>Проверена:</b> {session_info['last_verified_at'][:19] if session_info['last_verified_at'] else 'N/A'}

📝 <b>Заметки:</b> {session_info['notes'] or 'Нет'}
"""
    
    await message.answer(text, parse_mode="HTML")


# --- /admin_sessions command ---


@router.message(Command("admin_sessions"))
async def cmd_admin_sessions(message: Message) -> None:
    """Handle /admin_sessions command.
    
    Shows list of all sessions in database.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    sessions = await get_all_sessions()
    
    if not sessions:
        await message.answer(
            "📭 <b>Нет сессий в базе данных</b>\n\n"
            "Добавьте сессию: <code>/admin_set_session YOUR_TOKEN</code>",
            parse_mode="HTML"
        )
        return
    
    text = "📋 <b>История Instagram сессий</b>\n\n"
    
    for s in sessions:
        status = ""
        if s["is_active"] and s["is_valid"]:
            status = "✅ Активна"
        elif s["is_active"] and not s["is_valid"]:
            status = "⚠️ Активна, но невалидна"
        else:
            status = "❌ Неактивна"
        
        created = s["created_at"][:10] if s["created_at"] else "N/A"
        
        text += f"• <code>{s['session_id_masked']}</code> — {status}\n"
        text += f"  ID: {s['id']}, Создана: {created}\n\n"
    
    text += "\n<i>Показаны последние 10 сессий</i>"
    
    await message.answer(text, parse_mode="HTML")


# --- /admin_stats command ---


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    """Handle /admin_stats command.
    
    Shows bot statistics.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    from app.bot.http_client import api_get
    
    try:
        stats = await api_get(f"/admin/stats", headers={"X-User-Id": str(user_id)})
        
        text = f"""
📊 <b>Статистика бота</b>

👥 <b>Пользователи:</b>
• Всего: {stats['users']['total']}
• Активных: {stats['users']['active']}

🔍 <b>Проверки:</b>
• Всего: {stats['checks']['total']}
• Успешных: {stats['checks']['completed']}
• С ошибкой: {stats['checks']['failed']}
• В очереди: {stats['checks']['pending']}
• Success rate: {stats['checks']['success_rate']}%

💰 <b>Платежи:</b>
• Количество: {stats['payments']['total_count']}
• Сумма: {stats['payments']['total_revenue']:.2f}

🔑 <b>Instagram:</b>
• Статус сессии: {stats['instagram']['session_status']}
"""
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при получении статистики:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to get admin stats: {e}")


# --- /admin_help command ---


@router.message(Command("admin_help"))
async def cmd_admin_help(message: Message) -> None:
    """Handle /admin_help command.
    
    Shows available admin commands.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    text = """
🛠 <b>Админ-команды</b>

<b>Instagram сессия:</b>
• /admin_set_session &lt;token&gt; — установить новый токен
• /admin_check_session — проверить текущий токен
• /admin_sessions — история сессий

<b>Статистика:</b>
• /admin_stats — статистика бота

<b>Справка:</b>
• /admin_help — эта справка

<i>Для получения session_id:</i>
1. Войдите в Instagram через браузер
2. Откройте DevTools (F12)
3. Application → Cookies → instagram.com
4. Скопируйте значение <code>sessionid</code>
"""
    
    await message.answer(text, parse_mode="HTML")

