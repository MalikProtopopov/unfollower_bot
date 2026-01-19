"""Admin notification service for sending alerts to administrators."""

from datetime import datetime

import httpx

from app.config import get_settings
from app.utils.logger import logger

settings = get_settings()


class AdminNotifier:
    """Service for sending notifications to admins via Telegram Bot API."""
    
    def __init__(self, token: str | None = None):
        self.token = token or settings.effective_admin_bot_token
        self.base_url = f"https://api.telegram.org/bot{self.token}"
    
    async def send_message(
        self, 
        chat_id: int, 
        text: str, 
        parse_mode: str = "HTML",
    ) -> bool:
        """Send a message to a chat."""
        if not self.token:
            logger.warning("Admin bot token not configured, skipping notification")
            return False
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    }
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send admin notification to {chat_id}: {e}")
            return False
    
    async def notify_all_admins(self, text: str) -> int:
        """Send notification to all admin users."""
        admin_ids = settings.admin_ids
        if not admin_ids:
            logger.warning("No admin IDs configured for notifications")
            return 0
        
        sent_count = 0
        for admin_id in admin_ids:
            if await self.send_message(admin_id, text):
                sent_count += 1
        
        return sent_count


# Global notifier instance
_admin_notifier: AdminNotifier | None = None


def get_admin_notifier() -> AdminNotifier:
    """Get or create the global admin notifier instance."""
    global _admin_notifier
    if _admin_notifier is None:
        _admin_notifier = AdminNotifier()
    return _admin_notifier


# --- Notification Functions ---


async def notify_admin_new_purchase(
    user_id: int,
    username: str | None,
    tariff_name: str,
    amount: float,
    checks_count: int,
    payment_method: str,
) -> None:
    """Notify admins about a new purchase."""
    notifier = get_admin_notifier()
    
    user_mention = f"@{username}" if username else f"ID: {user_id}"
    
    text = f"""
💰 <b>Новая покупка!</b>

👤 Пользователь: {user_mention}
🆔 User ID: <code>{user_id}</code>

📦 Тариф: {tariff_name}
💵 Сумма: {amount} 
🔢 Проверок: {checks_count}
💳 Способ: {payment_method}

🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    await notifier.notify_all_admins(text)
    logger.info(f"Admin notified about purchase from user {user_id}")


async def notify_admin_check_started(
    user_id: int,
    username: str | None,
    target_username: str,
    check_id: str,
) -> None:
    """Notify admins about a new check being started."""
    notifier = get_admin_notifier()
    
    user_mention = f"@{username}" if username else f"ID: {user_id}"
    
    text = f"""
🔍 <b>Новая проверка</b>

👤 Пользователь: {user_mention}
🆔 User ID: <code>{user_id}</code>

📱 Аккаунт: @{target_username}
🔖 Check ID: <code>{check_id[:8]}...</code>

🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    await notifier.notify_all_admins(text)


async def notify_admin_check_error(
    user_id: int,
    username: str | None,
    target_username: str,
    check_id: str,
    error_type: str,
    error_message: str,
) -> None:
    """Notify admins about an error during check processing."""
    notifier = get_admin_notifier()
    
    user_mention = f"@{username}" if username else f"ID: {user_id}"
    
    # Determine error severity
    is_session_error = any(x in error_message.lower() for x in [
        "401", "unauthorized", "session", "login", "authentication"
    ])
    
    error_emoji = "🚨" if is_session_error else "⚠️"
    
    text = f"""
{error_emoji} <b>Ошибка при проверке!</b>

👤 Пользователь: {user_mention}
🆔 User ID: <code>{user_id}</code>
📱 Аккаунт: @{target_username}
🔖 Check ID: <code>{check_id[:8]}...</code>

❌ <b>Тип ошибки:</b> {error_type}
📝 <b>Сообщение:</b>
<code>{error_message}</code>

🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    if is_session_error:
        text += """

🔴 <b>ВНИМАНИЕ:</b> Возможно, истек session_id!
Используйте API для обновления:
<code>POST /api/v1/admin/session</code>
"""
    
    await notifier.notify_all_admins(text)
    logger.warning(f"Admin notified about check error for user {user_id}: {error_type}")


async def notify_admin_session_error() -> None:
    """Notify admins that Instagram session has expired or is invalid."""
    notifier = get_admin_notifier()
    
    text = f"""
🚨🚨🚨 <b>КРИТИЧЕСКАЯ ОШИБКА!</b> 🚨🚨🚨

Instagram Session ID истёк или недействителен!

Все проверки будут завершаться с ошибкой до обновления.

<b>Для обновления:</b>
1. Войдите в Instagram через браузер
2. Скопируйте cookie <code>sessionid</code>
3. Обновите через API:

<code>POST /api/v1/admin/session
{{"session_id": "YOUR_NEW_SESSION_ID"}}</code>

🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    await notifier.notify_all_admins(text)
    logger.critical("Admin notified about session expiry!")


async def notify_admin_check_completed(
    user_id: int,
    username: str | None,
    target_username: str,
    followers_count: int,
    following_count: int,
    non_mutual_count: int,
) -> None:
    """Notify admins about a successfully completed check."""
    notifier = get_admin_notifier()
    
    user_mention = f"@{username}" if username else f"ID: {user_id}"
    
    text = f"""
✅ <b>Проверка завершена</b>

👤 Пользователь: {user_mention}
📱 Аккаунт: @{target_username}

📊 <b>Результаты:</b>
• Подписчиков: {followers_count:,}
• Подписок: {following_count:,}
• Не взаимных: {non_mutual_count:,}

🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
"""
    
    await notifier.notify_all_admins(text)


async def notify_admin(message: str) -> None:
    """Simple convenience function to send a message to all admins.
    
    Args:
        message: Text message to send (supports HTML formatting)
    """
    notifier = get_admin_notifier()
    await notifier.notify_all_admins(message)

