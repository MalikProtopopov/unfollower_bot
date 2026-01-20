"""Background check processing service."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.config import get_instagram_session_id, get_settings
from app.models.database import async_session_maker
from app.models.models import Check, CheckStatusEnum, FileTypeEnum, NonMutualUser, User
from app.services.admin_notification_service import (
    notify_admin_check_completed,
    notify_admin_check_error,
    notify_admin_check_started,
    notify_admin_session_error,
)
from app.services.file_generator import generate_xlsx_report
from app.services.instagram_scraper import (
    InstagramScraper,
    InstagramScraperError,
    PrivateAccountError,
    RateLimitError,
    UserNotFoundError,
)
from app.services.notification_service import notify_check_completed
from app.utils.logger import logger

settings = get_settings()


async def refund_check_balance(user_id: int, reason: str) -> bool:
    """Refund one check to user's balance when check fails.
    
    Args:
        user_id: User ID to refund
        reason: Reason for refund
        
    Returns:
        True if refund was successful
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.checks_balance += 1
            await session.commit()
            logger.info(
                f"Refunded 1 check to user {user_id}. "
                f"Reason: {reason}. New balance: {user.checks_balance}"
            )
            return True
        return False


async def get_check_with_user(check_id: str) -> tuple[Check | None, User | None]:
    """Get check and associated user from database."""
    async with async_session_maker() as session:
        result = await session.execute(
            select(Check).where(Check.check_id == uuid.UUID(check_id))
        )
        check = result.scalar_one_or_none()
        
        if not check:
            return None, None
        
        user_result = await session.execute(
            select(User).where(User.user_id == check.user_id)
        )
        user = user_result.scalar_one_or_none()
        
        return check, user


async def update_check_status(
    check_id: str,
    status: CheckStatusEnum | None = None,
    progress: int | None = None,
    error_message: str | None = None,
    **kwargs,
):
    """Update check status in database.

    Args:
        check_id: Check UUID
        status: New status
        progress: Progress percentage
        error_message: Error message if failed
        **kwargs: Additional fields to update
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(Check).where(Check.check_id == uuid.UUID(check_id))
        )
        check = result.scalar_one_or_none()

        if check:
            if status:
                check.status = status
            if progress is not None:
                check.progress = progress
            if error_message:
                check.error_message = error_message

            for key, value in kwargs.items():
                if hasattr(check, key):
                    setattr(check, key, value)

            await session.commit()


async def save_non_mutual_users(check_id: str, non_mutual_users: list):
    """Save non-mutual users to database.

    Args:
        check_id: Check UUID
        non_mutual_users: List of InstagramUser objects
    """
    async with async_session_maker() as session:
        for user in non_mutual_users:
            non_mutual = NonMutualUser(
                check_id=uuid.UUID(check_id),
                target_user_id=user.user_id,
                target_username=user.username,
                target_full_name=user.full_name,
                target_avatar_url=user.avatar_url,
                user_follows_target=True,
                target_follows_user=False,
                is_mutual=False,
            )
            session.add(non_mutual)

        await session.commit()
        logger.info(f"Saved {len(non_mutual_users)} non-mutual users for check {check_id}")


async def process_check(check_id: str):
    """Process a followers check in background.

    This function:
    1. Fetches followers and following from Instagram
    2. Calculates non-mutual followers
    3. Saves results to database
    4. Generates XLSX report
    5. Sends notifications to user and admins

    Args:
        check_id: Check UUID string
    """
    logger.info(f"Starting check processing: {check_id}")

    # Get check details with user
    check, user = await get_check_with_user(check_id)

    if not check:
        logger.error(f"Check {check_id} not found")
        return

    target_username = check.target_username
    user_id = check.user_id
    username = user.username if user else None

    # Notify admins about check start
    await notify_admin_check_started(user_id, username, target_username, check_id)

    # Update status to processing
    await update_check_status(check_id, status=CheckStatusEnum.PROCESSING, progress=0)

    # Get current session ID (mutable)
    session_id = get_instagram_session_id()
    
    # Initialize scraper with slower delays to avoid Instagram blocking
    scraper = InstagramScraper(
        session_id=session_id if session_id else None,
        max_retries=3,
        delay_range=(4.0, 8.0),  # Increased delays to prevent account blocking
    )

    try:
        # Progress callback
        async def on_progress(progress: int, message: str):
            await update_check_status(check_id, progress=progress)
            logger.info(f"Check {check_id}: {message} ({progress}%)")

        # Fetch data
        followers, following, non_mutual = await scraper.get_non_mutual_followers(
            username=target_username,
            max_users=10000,
            on_progress=lambda p, m: None,  # Sync callback, handle async separately
        )

        # Update session last used timestamp
        from app.services.session_service import update_session_last_used
        if session_id:
            await update_session_last_used(session_id)

        # Detect suspicious/empty results (likely expired token or API error)
        if len(followers) == 0 and len(following) == 0:
            # Both lists empty - very suspicious, likely session expired
            error_msg = "Не удалось получить данные Instagram. Попробуйте позже или обратитесь к менеджеру."
            logger.error(
                f"Check {check_id} detected empty results: 0 followers, 0 following. "
                f"Likely session expired or API error."
            )
            
            # Mark session as potentially invalid and notify admin
            from app.services.session_service import mark_session_invalid
            await mark_session_invalid(session_id)
            await notify_admin_session_error()
            
            await update_check_status(
                check_id,
                status=CheckStatusEnum.FAILED,
                error_message=error_msg,
            )
            # Refund balance - user shouldn't pay for failed check
            await refund_check_balance(user_id, "EmptyResults: 0 followers and 0 following")
            await notify_check_completed(check_id)
            await notify_admin_check_error(
                user_id, username, target_username, check_id,
                "EmptyResults", "Received 0 followers and 0 following - possible session expiry"
            )
            return
        
        if len(followers) == 0 and len(following) > 0:
            # Got following but no followers - API error or rate limiting
            error_msg = "Ошибка при получении списка подписчиков. Попробуйте позже."
            logger.error(
                f"Check {check_id} detected partial results: 0 followers, {len(following)} following. "
                f"Possible API error or rate limiting."
            )
            
            await update_check_status(
                check_id,
                status=CheckStatusEnum.FAILED,
                error_message=error_msg,
            )
            # Refund balance - incomplete data
            await refund_check_balance(user_id, f"EmptyFollowers: 0 followers, {len(following)} following")
            await notify_check_completed(check_id)
            await notify_admin_check_error(
                user_id, username, target_username, check_id,
                "EmptyFollowers", f"Received 0 followers but {len(following)} following"
            )
            return

        # Update progress
        await update_check_status(check_id, progress=70)

        # Save non-mutual users to database
        await save_non_mutual_users(check_id, non_mutual)
        await update_check_status(check_id, progress=80)

        # Generate XLSX report
        file_path = await generate_xlsx_report(
            check_id=check_id,
            target_username=target_username,
            followers=followers,
            following=following,
            non_mutual=non_mutual,
        )
        await update_check_status(check_id, progress=95)

        # Get file size
        import os
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

        # Update check as completed
        await update_check_status(
            check_id,
            status=CheckStatusEnum.COMPLETED,
            progress=100,
            total_subscriptions=len(following),
            total_followers=len(followers),
            total_non_mutual=len(non_mutual),
            file_path=file_path,
            file_type=FileTypeEnum.XLSX,
            file_size=file_size,
            completed_at=datetime.now(timezone.utc),
        )

        logger.info(
            f"Check {check_id} completed: "
            f"{len(followers)} followers, {len(following)} following, "
            f"{len(non_mutual)} non-mutual"
        )
        
        # Send notification to user
        await notify_check_completed(check_id)
        
        # Notify admins about completion
        await notify_admin_check_completed(
            user_id, username, target_username,
            len(followers), len(following), len(non_mutual)
        )

    except UserNotFoundError as e:
        error_msg = f"Пользователь @{target_username} не найден"
        logger.error(f"Check {check_id} failed: User not found - {e}")
        await update_check_status(
            check_id,
            status=CheckStatusEnum.FAILED,
            error_message=error_msg,
        )
        # Refund balance since check failed
        await refund_check_balance(user_id, f"UserNotFound: {target_username}")
        await notify_check_completed(check_id)
        await notify_admin_check_error(user_id, username, target_username, check_id, "UserNotFound", str(e))

    except PrivateAccountError as e:
        error_msg = f"Аккаунт @{target_username} закрыт (приватный)"
        logger.error(f"Check {check_id} failed: Private account - {e}")
        await update_check_status(
            check_id,
            status=CheckStatusEnum.FAILED,
            error_message=error_msg,
        )
        # Refund balance since check failed
        await refund_check_balance(user_id, f"PrivateAccount: {target_username}")
        await notify_check_completed(check_id)
        await notify_admin_check_error(user_id, username, target_username, check_id, "PrivateAccount", str(e))

    except RateLimitError as e:
        error_msg = "Instagram временно ограничил доступ. Попробуйте позже."
        logger.error(f"Check {check_id} failed: Rate limited - {e}")
        await update_check_status(
            check_id,
            status=CheckStatusEnum.FAILED,
            error_message=error_msg,
        )
        # Refund balance since check failed
        await refund_check_balance(user_id, f"RateLimit: {target_username}")
        await notify_check_completed(check_id)
        await notify_admin_check_error(user_id, username, target_username, check_id, "RateLimit", str(e))

    except InstagramScraperError as e:
        error_str = str(e)
        error_msg = f"Ошибка при получении данных: {error_str}"
        logger.error(f"Check {check_id} failed: Scraper error - {e}")
        
        # Check if this is a session/auth error
        is_session_error = any(x in error_str.lower() for x in [
            "401", "unauthorized", "session", "login", "authentication", "please wait"
        ])
        
        if is_session_error:
            error_msg = "Ошибка авторизации Instagram. Мы уже работаем над решением проблемы."
            # Notify admins about session issue
            await notify_admin_session_error()
        
        await update_check_status(
            check_id,
            status=CheckStatusEnum.FAILED,
            error_message=error_msg,
        )
        # Refund balance since check failed
        await refund_check_balance(user_id, f"ScraperError: {target_username}")
        await notify_check_completed(check_id)
        await notify_admin_check_error(user_id, username, target_username, check_id, "ScraperError", error_str)

    except Exception as e:
        error_str = str(e)
        error_msg = "Произошла непредвиденная ошибка. Попробуйте позже."
        logger.exception(f"Check {check_id} failed with unexpected error: {e}")
        
        # Check if this might be a session error
        is_session_error = any(x in error_str.lower() for x in [
            "401", "unauthorized", "session", "login", "authentication"
        ])
        
        if is_session_error:
            await notify_admin_session_error()
        
        await update_check_status(
            check_id,
            status=CheckStatusEnum.FAILED,
            error_message=error_msg,
        )
        # Refund balance since check failed
        await refund_check_balance(user_id, f"UnexpectedError: {target_username}")
        await notify_check_completed(check_id)
        await notify_admin_check_error(user_id, username, target_username, check_id, "UnexpectedError", error_str)

    finally:
        await scraper.close()
