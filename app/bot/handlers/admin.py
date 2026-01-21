"""Admin command handlers for bot management.

Provides commands for admin users to manage Instagram sessions,
view statistics, and perform administrative tasks.
"""

from datetime import datetime
from urllib.parse import unquote

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.http_client import api_get
from app.config import get_settings
from app.services.session_service import (
    get_active_session_id,
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
    
    # Save to database directly without pre-validation
    # Instagram API is unreliable for validation, real check happens on first use
    try:
        session = await save_session_id(
            session_id=new_session_id,
            notes=f"Set by admin {user_id} via Telegram"
        )
        
        await message.answer(
            f"✅ <b>Токен установлен и сохранён!</b>\n\n"
            f"🔑 Session: <code>{masked}</code>\n"
            f"🆔 ID в базе: {session.id}\n"
            f"📅 Создан: {session.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Токен будет использоваться для всех проверок.\n"
            f"Валидность проверится при первой проверке аккаунта.",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} set new Instagram session (DB ID: {session.id})")
        
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


# --- /admin_daily command ---


@router.message(Command("admin_daily"))
async def cmd_admin_daily(message: Message) -> None:
    """Handle /admin_daily [DD.MM.YYYY] command.
    
    Shows daily statistics for a specific date.
    If no date provided, shows today's stats.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    # Parse optional date argument
    parts = message.text.split(maxsplit=1)
    target_date = None
    display_date = "сегодня"
    
    if len(parts) > 1 and parts[1].strip():
        date_str = parts[1].strip()
        try:
            # Parse DD.MM.YYYY format
            parsed_date = datetime.strptime(date_str, "%d.%m.%Y")
            target_date = parsed_date.strftime("%Y-%m-%d")
            display_date = date_str
        except ValueError:
            await message.answer(
                "❌ <b>Неверный формат даты!</b>\n\n"
                "Используйте: <code>/admin_daily ДД.ММ.ГГГГ</code>\n"
                "Пример: <code>/admin_daily 20.01.2026</code>",
                parse_mode="HTML"
            )
            return
    
    await message.answer(f"⏳ Загружаю статистику за {display_date}...")
    
    try:
        params = {}
        if target_date:
            params["target_date"] = target_date
        
        stats = await api_get(
            "/admin/stats/daily",
            params=params,
            headers={"X-User-Id": str(user_id)}
        )
        
        # Format display date from response
        resp_date = stats.get("date", display_date)
        try:
            formatted_date = datetime.strptime(resp_date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            formatted_date = resp_date
        
        text = f"""
📊 <b>Статистика за {formatted_date}</b>

👥 Новых пользователей: <b>{stats['new_users_count']}</b>
🛒 Куплено проверок: <b>{stats['checks_purchased']}</b>
✅ Выполнено проверок: <b>{stats['checks_completed']}</b>
⭐ Получено звёзд: <b>{stats['stars_received']}</b> XTR
💵 Получено рублей: <b>{stats['rubles_received']:.2f}</b> ₽
❌ Неудачных проверок: <b>{stats['checks_failed']}</b>
"""
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при получении статистики:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to get daily stats: {e}")


# --- /admin_failed command ---


@router.message(Command("admin_failed"))
async def cmd_admin_failed(message: Message) -> None:
    """Handle /admin_failed command.
    
    Shows list of failed checks with user information.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    await message.answer("⏳ Загружаю список неудачных проверок...")
    
    try:
        data = await api_get(
            "/admin/checks/failed",
            params={"limit": 15},
            headers={"X-User-Id": str(user_id)}
        )
        
        failed_checks = data.get("failed_checks", [])
        
        if not failed_checks:
            await message.answer(
                "✅ <b>Нет неудачных проверок!</b>\n\n"
                "Все проверки прошли успешно.",
                parse_mode="HTML"
            )
            return
        
        text = "❌ <b>Последние неудачные проверки</b>\n\n"
        
        for i, check in enumerate(failed_checks, 1):
            user_tg = check.get("user_username", "unknown")
            target_insta = check.get("target_username", "unknown")
            error = check.get("error_message", "Unknown error")
            created_at = check.get("created_at", "")
            
            # Format datetime
            try:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                formatted_dt = dt.strftime("%d.%m.%Y %H:%M")
            except (ValueError, AttributeError):
                formatted_dt = created_at[:16] if created_at else "N/A"
            
            # Truncate long error messages
            if len(error) > 50:
                error = error[:47] + "..."
            
            text += f"<b>{i}.</b> @{user_tg} → @{target_insta}\n"
            text += f"   📅 {formatted_dt}\n"
            text += f"   💬 {error}\n\n"
        
        text += f"<i>Показано {len(failed_checks)} из последних проверок</i>"
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при получении данных:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to get failed checks: {e}")


# --- Auto-refresh commands ---


@router.message(Command("admin_set_credentials"))
async def cmd_admin_set_credentials(message: Message) -> None:
    """Handle /admin_set_credentials <username> <password> command.
    
    Saves Instagram credentials for automatic session refresh.
    Credentials are encrypted before storage.
    
    IMPORTANT: Delete the message after sending for security!
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    # Parse arguments
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/admin_set_credentials username password</code>\n\n"
            "⚠️ <b>Безопасность:</b> После отправки удалите сообщение с паролем!",
            parse_mode="HTML"
        )
        return
    
    username = parts[1].strip()
    password = parts[2].strip()
    
    # Try to delete the message with password for security
    try:
        await message.delete()
        deleted_msg = "✅ Сообщение с паролем удалено."
    except Exception:
        deleted_msg = "⚠️ Не удалось удалить сообщение. Удалите его вручную!"
    
    await message.answer(f"⏳ Сохраняю credentials для {username}...")
    
    try:
        from app.services.session_refresh_service import get_refresh_service
        
        refresh_service = get_refresh_service()
        credentials = await refresh_service.save_credentials(
            username=username,
            password=password,
        )
        
        await message.answer(
            f"✅ <b>Credentials сохранены!</b>\n\n"
            f"👤 Username: <code>{username}</code>\n"
            f"🔐 Password: ••••••••\n"
            f"📅 Сохранено: {credentials.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"{deleted_msg}\n\n"
            f"Теперь сессия будет обновляться автоматически.\n"
            f"Для принудительного обновления: /admin_refresh_session",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} set credentials for {username}")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при сохранении:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to save credentials: {e}")


@router.message(Command("admin_set_credentials_2fa"))
async def cmd_admin_set_credentials_2fa(message: Message) -> None:
    """Handle /admin_set_credentials_2fa <username> <password> <totp_secret> command.
    
    Saves Instagram credentials with 2FA TOTP secret for automatic session refresh.
    
    IMPORTANT: Delete the message after sending for security!
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    # Parse arguments
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "❌ <b>Использование:</b>\n"
            "<code>/admin_set_credentials_2fa username password totp_secret</code>\n\n"
            "TOTP secret — это ключ для генерации кодов 2FA.\n"
            "Его можно получить при настройке 2FA в Instagram.\n\n"
            "⚠️ <b>Безопасность:</b> После отправки удалите сообщение!",
            parse_mode="HTML"
        )
        return
    
    username = parts[1].strip()
    password = parts[2].strip()
    totp_secret = parts[3].strip()
    
    # Try to delete the message with credentials for security
    try:
        await message.delete()
        deleted_msg = "✅ Сообщение с credentials удалено."
    except Exception:
        deleted_msg = "⚠️ Не удалось удалить сообщение. Удалите его вручную!"
    
    await message.answer(f"⏳ Сохраняю credentials с 2FA для {username}...")
    
    try:
        from app.services.session_refresh_service import get_refresh_service
        
        refresh_service = get_refresh_service()
        credentials = await refresh_service.save_credentials(
            username=username,
            password=password,
            totp_secret=totp_secret,
        )
        
        await message.answer(
            f"✅ <b>Credentials с 2FA сохранены!</b>\n\n"
            f"👤 Username: <code>{username}</code>\n"
            f"🔐 Password: ••••••••\n"
            f"🔑 TOTP: Настроен\n"
            f"📅 Сохранено: {credentials.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"{deleted_msg}\n\n"
            f"Теперь сессия будет обновляться автоматически с поддержкой 2FA.",
            parse_mode="HTML"
        )
        logger.info(f"Admin {user_id} set credentials with 2FA for {username}")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка при сохранении:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to save credentials with 2FA: {e}")


@router.message(Command("admin_refresh_session"))
async def cmd_admin_refresh_session(message: Message) -> None:
    """Handle /admin_refresh_session command.
    
    Manually triggers session refresh using saved credentials.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    await message.answer(
        "⏳ <b>Запускаю обновление сессии...</b>\n\n"
        "Это может занять 10-30 секунд.\n"
        "Пожалуйста, подождите.",
        parse_mode="HTML"
    )
    
    try:
        from app.services.session_refresh_service import get_refresh_service
        
        refresh_service = get_refresh_service()
        
        # Check if credentials exist
        credentials = await refresh_service.get_active_credentials()
        if not credentials:
            await message.answer(
                "❌ <b>Credentials не настроены!</b>\n\n"
                "Сначала установите credentials:\n"
                "<code>/admin_set_credentials username password</code>",
                parse_mode="HTML"
            )
            return
        
        # Perform refresh
        success, result_message = await refresh_service.refresh_session()
        
        if success:
            await message.answer(
                f"✅ <b>Сессия успешно обновлена!</b>\n\n"
                f"👤 Account: {credentials.username}\n"
                f"📝 {result_message}\n\n"
                f"Новая сессия будет использоваться для всех проверок.",
                parse_mode="HTML"
            )
            logger.info(f"Admin {user_id} manually refreshed session successfully")
        else:
            await message.answer(
                f"❌ <b>Ошибка обновления сессии!</b>\n\n"
                f"📝 {result_message}\n\n"
                f"Проверьте credentials и попробуйте снова.\n"
                f"Если включена 2FA, используйте /admin_set_credentials_2fa",
                parse_mode="HTML"
            )
            logger.error(f"Admin {user_id} manual session refresh failed: {result_message}")
            
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Manual session refresh error: {e}")


@router.message(Command("admin_refresh_status"))
async def cmd_admin_refresh_status(message: Message) -> None:
    """Handle /admin_refresh_status command.
    
    Shows status of automatic session refresh system.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    try:
        from app.services.session_refresh_service import get_refresh_service
        from app.services.session_service import get_session_info
        
        refresh_service = get_refresh_service()
        credentials = await refresh_service.get_active_credentials()
        session_info = await get_session_info()
        
        # Credentials status
        if credentials:
            creds_status = f"✅ Настроены для: <code>{credentials.username}</code>"
            creds_last_used = credentials.last_used_at.strftime('%d.%m.%Y %H:%M') if credentials.last_used_at else "Никогда"
            creds_success = "✅ Да" if credentials.last_login_success else ("❌ Нет" if credentials.last_login_success is False else "⏳ Ещё не было")
            creds_error = credentials.last_error[:50] + "..." if credentials.last_error and len(credentials.last_error) > 50 else (credentials.last_error or "Нет")
        else:
            creds_status = "❌ Не настроены"
            creds_last_used = "—"
            creds_success = "—"
            creds_error = "—"
        
        # Session status
        if session_info:
            session_status = "✅ Активна" if session_info.get("is_active") and session_info.get("is_valid") else "⚠️ Проблема"
            session_masked = session_info.get("session_id_masked", "N/A")
            session_created = session_info.get("created_at", "")[:19] if session_info.get("created_at") else "N/A"
            next_refresh = session_info.get("next_refresh_at", "")[:19] if session_info.get("next_refresh_at") else "Не запланировано"
            fail_count = session_info.get("fail_count", 0)
            last_error = session_info.get("last_error") or "Нет"
            if len(last_error) > 50:
                last_error = last_error[:47] + "..."
        else:
            session_status = "❌ Нет активной сессии"
            session_masked = "—"
            session_created = "—"
            next_refresh = "—"
            fail_count = 0
            last_error = "—"
        
        text = f"""
🔄 <b>Статус Auto-Refresh</b>

<b>📱 Credentials:</b>
• Статус: {creds_status}
• Последнее использование: {creds_last_used}
• Успешный логин: {creds_success}
• Последняя ошибка: {creds_error}

<b>🔑 Текущая сессия:</b>
• Статус: {session_status}
• Token: <code>{session_masked}</code>
• Создана: {session_created}

<b>🕐 Автообновление:</b>
• Следующее: {next_refresh}
• Количество ошибок: {fail_count}
• Последняя ошибка: {last_error}

<b>Команды:</b>
• /admin_refresh_session — обновить сейчас
• /admin_set_credentials — задать credentials
"""
        
        await message.answer(text, parse_mode="HTML")
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to get refresh status: {e}")


@router.message(Command("admin_clear_credentials"))
async def cmd_admin_clear_credentials(message: Message) -> None:
    """Handle /admin_clear_credentials command.
    
    Clears saved Instagram credentials.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    try:
        from sqlalchemy import update
        from app.models.database import async_session_maker
        from app.models.models import RefreshCredentials
        
        async with async_session_maker() as session:
            result = await session.execute(
                update(RefreshCredentials)
                .where(RefreshCredentials.is_active == True)
                .values(is_active=False)
            )
            await session.commit()
            
            if result.rowcount > 0:
                await message.answer(
                    "✅ <b>Credentials удалены!</b>\n\n"
                    "Автоматическое обновление сессии отключено.\n"
                    "Для настройки: /admin_set_credentials",
                    parse_mode="HTML"
                )
                logger.info(f"Admin {user_id} cleared credentials")
            else:
                await message.answer(
                    "ℹ️ Нет активных credentials для удаления.",
                    parse_mode="HTML"
                )
                
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка:</b>\n{str(e)}",
            parse_mode="HTML"
        )
        logger.error(f"Failed to clear credentials: {e}")


# --- /admin_help command ---


@router.message(Command("admin_help"))
@router.message(Command("help"))
async def cmd_admin_help(message: Message) -> None:
    """Handle /admin_help and /help commands.
    
    Shows available admin commands.
    """
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    text = """
🛠 <b>Админ-команды</b>

<b>Instagram сессия:</b>
• /admin_set_session &lt;token&gt; — установить токен вручную
• /admin_check_session — проверить текущий токен
• /admin_sessions — история сессий

<b>🔄 Auto-Refresh (автообновление):</b>
• /admin_set_credentials &lt;user&gt; &lt;pass&gt; — задать логин/пароль
• /admin_set_credentials_2fa &lt;user&gt; &lt;pass&gt; &lt;totp&gt; — с 2FA
• /admin_refresh_session — обновить сессию сейчас
• /admin_refresh_status — статус автообновления
• /admin_clear_credentials — удалить credentials

<b>Статистика:</b>
• /admin_stats — общая статистика бота
• /admin_daily [ДД.ММ.ГГГГ] — статистика за день
• /admin_failed — список неудачных проверок

<b>Справка:</b>
• /admin_help — эта справка

<i>⚠️ При отправке credentials — удалите сообщение после!</i>
"""
    
    await message.answer(text, parse_mode="HTML")

