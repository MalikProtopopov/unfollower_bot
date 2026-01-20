"""Notification service for sending Telegram messages after check completion."""

import json
import uuid
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import get_settings
from app.models.database import async_session_maker
from app.models.models import Check, CheckStatusEnum, User
from app.utils.logger import logger
from sqlalchemy import select

settings = get_settings()


class TelegramNotifier:
    """Service for sending Telegram notifications using Bot API directly."""
    
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
    
    async def send_message(
        self, 
        chat_id: int, 
        text: str, 
        parse_mode: str = "HTML",
        reply_markup: dict | None = None
    ) -> bool:
        """Send a text message to a chat.
        
        Args:
            chat_id: Telegram chat ID
            text: Message text
            parse_mode: Parse mode (HTML, Markdown, etc.)
            reply_markup: Optional inline keyboard markup
            
        Returns:
            True if message was sent successfully
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                data = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
                if reply_markup:
                    data["reply_markup"] = json.dumps(reply_markup)
                    
                response = await client.post(
                    f"{self.base_url}/sendMessage",
                    json=data
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send message to {chat_id}: {e}")
            return False
    
    async def send_document(
        self,
        chat_id: int,
        document_path: str,
        caption: str | None = None,
        parse_mode: str = "HTML"
    ) -> bool:
        """Send a document to a chat.
        
        Args:
            chat_id: Telegram chat ID
            document_path: Path to the document file
            caption: Optional caption for the document
            parse_mode: Parse mode for caption
            
        Returns:
            True if document was sent successfully
        """
        try:
            path = Path(document_path)
            if not path.exists():
                logger.error(f"Document not found: {document_path}")
                return False
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(path, "rb") as f:
                    files = {"document": (path.name, f, "application/octet-stream")}
                    data = {"chat_id": chat_id}
                    if caption:
                        data["caption"] = caption
                        data["parse_mode"] = parse_mode
                    
                    response = await client.post(
                        f"{self.base_url}/sendDocument",
                        data=data,
                        files=files
                    )
                    response.raise_for_status()
                    return True
        except Exception as e:
            logger.error(f"Failed to send document to {chat_id}: {e}")
            return False


# Global notifier instance
_notifier: TelegramNotifier | None = None


def get_notifier() -> TelegramNotifier:
    """Get or create the global notifier instance."""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier(settings.telegram_token)
    return _notifier


def get_manager_contact_url(check_id: str, target_username: str, error_message: str) -> str:
    """Generate URL for contacting manager with pre-filled message."""
    manager = settings.manager_username
    message = (
        f"Здравствуйте! У меня возникла ошибка при проверке аккаунта @{target_username}.\n\n"
        f"ID проверки: {check_id[:8]}...\n"
        f"Ошибка: {error_message[:100]}\n\n"
        f"Прошу помочь разобраться с проблемой."
    )
    return f"https://t.me/{manager}?text={quote(message)}"


async def notify_check_completed(check_id: str) -> bool:
    """Send notification to user when their check is completed.
    
    Args:
        check_id: The check UUID string
        
    Returns:
        True if notification was sent successfully
    """
    notifier = get_notifier()
    
    async with async_session_maker() as session:
        # Get check with user
        result = await session.execute(
            select(Check).where(Check.check_id == uuid.UUID(check_id))
        )
        check = result.scalar_one_or_none()
        
        if not check:
            logger.error(f"Check {check_id} not found for notification")
            return False
        
        # Get user
        user_result = await session.execute(
            select(User).where(User.user_id == check.user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User {check.user_id} not found for notification")
            return False
        
        if check.status == CheckStatusEnum.COMPLETED:
            # Success notification
            mutual_count = (check.total_subscriptions or 0) - (check.total_non_mutual or 0)
            mutual_percent = (
                (mutual_count / check.total_subscriptions * 100) 
                if check.total_subscriptions else 0
            )
            
            text = f"""
✅ <b>Проверка завершена!</b>

📋 Аккаунт: <b>@{check.target_username}</b>

📊 <b>Результаты:</b>
• Подписчиков: <b>{check.total_followers or 0:,}</b>
• Подписок: <b>{check.total_subscriptions or 0:,}</b>
• Взаимных: <b>{mutual_count:,}</b> ({mutual_percent:.1f}%)
• Не взаимных: <b>{check.total_non_mutual or 0:,}</b>

📄 Отчёт в Excel файле ниже 👇
"""
            # Send message
            message_sent = await notifier.send_message(user.user_id, text)
            
            # Send file if exists
            if check.file_path and Path(check.file_path).exists():
                await notifier.send_document(
                    user.user_id,
                    check.file_path,
                    caption="📊 Подробный отчёт о подписках"
                )
            
            logger.info(f"Sent completion notification for check {check_id} to user {user.user_id}")
            return message_sent
            
        elif check.status == CheckStatusEnum.FAILED:
            # Error notification with manager contact button
            error_message = check.error_message or "Неизвестная ошибка"
            manager_url = get_manager_contact_url(check_id, check.target_username, error_message)
            
            text = f"""
❌ <b>Проверка завершилась с ошибкой</b>

📋 Аккаунт: <b>@{check.target_username}</b>

⚠️ <b>Ошибка:</b>
{error_message}

✅ <b>Проверка возвращена на баланс</b> — вы не потеряли проверку.

Если проблема повторяется, свяжитесь с менеджером — мы поможем решить вопрос!
"""
            # Inline keyboard with manager contact button
            reply_markup = {
                "inline_keyboard": [
                    [
                        {
                            "text": "💬 Написать менеджеру",
                            "url": manager_url
                        }
                    ],
                    [
                        {
                            "text": "🔄 Попробовать снова",
                            "callback_data": "start_check"
                        }
                    ],
                    [
                        {
                            "text": "🏠 Главное меню",
                            "callback_data": "main_menu"
                        }
                    ]
                ]
            }
            
            message_sent = await notifier.send_message(user.user_id, text, reply_markup=reply_markup)
            logger.info(f"Sent failure notification for check {check_id} to user {user.user_id}")
            return message_sent
    
    return False


async def notify_referral_bonus(user_id: int, bonus_checks: int) -> bool:
    """Send notification when user receives referral bonus.
    
    Args:
        user_id: User ID to notify
        bonus_checks: Number of bonus checks earned
        
    Returns:
        True if notification was sent successfully
    """
    notifier = get_notifier()
    
    text = f"""
🎉 <b>Поздравляем!</b>

Вы получили <b>{bonus_checks}</b> бесплатную проверку за приглашение друзей!

Продолжайте приглашать друзей и получайте больше бонусов.
Используйте /referral чтобы увидеть вашу реферальную ссылку.
"""
    
    success = await notifier.send_message(user_id, text)
    if success:
        logger.info(f"Sent referral bonus notification to user {user_id}")
    return success


async def notify_new_referral(referrer_id: int, referred_username: str | None) -> bool:
    """Send notification when someone registers using user's referral link.
    
    Args:
        referrer_id: ID of the user who made the referral
        referred_username: Username of the new user (if available)
        
    Returns:
        True if notification was sent successfully
    """
    notifier = get_notifier()
    
    user_mention = f"@{referred_username}" if referred_username else "Новый пользователь"
    
    text = f"""
👤 <b>Новый реферал!</b>

{user_mention} присоединился по вашей ссылке.

Используйте /referral чтобы увидеть прогресс до бонусной проверки.
"""
    
    success = await notifier.send_message(referrer_id, text)
    if success:
        logger.info(f"Sent new referral notification to user {referrer_id}")
    return success
