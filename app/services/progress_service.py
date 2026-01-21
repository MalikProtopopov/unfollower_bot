"""Check progress service for resume functionality.

Handles saving and restoring check progress to allow resuming
interrupted checks after session refresh.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update, delete

from app.models.database import async_session_maker
from app.models.models import CheckProgress, CheckProgressStatusEnum
from app.utils.logger import logger


async def save_progress(
    check_id: uuid.UUID,
    followers_cursor: str | None = None,
    following_cursor: str | None = None,
    followers_fetched: int = 0,
    following_fetched: int = 0,
    followers_data: list[dict] | None = None,
    following_data: list[dict] | None = None,
    status: CheckProgressStatusEnum = CheckProgressStatusEnum.IN_PROGRESS,
) -> CheckProgress:
    """Save check progress to database.
    
    This allows resuming the check if it's interrupted (e.g., session expiry).
    
    Args:
        check_id: Check UUID.
        followers_cursor: Pagination cursor for followers.
        following_cursor: Pagination cursor for following.
        followers_fetched: Number of followers already fetched.
        following_fetched: Number of following already fetched.
        followers_data: List of fetched followers (as dicts).
        following_data: List of fetched following (as dicts).
        status: Progress status.
        
    Returns:
        CheckProgress record.
    """
    async with async_session_maker() as session:
        # Check if progress record exists
        result = await session.execute(
            select(CheckProgress)
            .where(CheckProgress.check_id == check_id)
            .limit(1)
        )
        progress = result.scalar_one_or_none()
        
        if progress:
            # Update existing
            progress.followers_cursor = followers_cursor
            progress.following_cursor = following_cursor
            progress.followers_fetched = followers_fetched
            progress.following_fetched = following_fetched
            progress.followers_data = followers_data
            progress.following_data = following_data
            progress.status = status
            progress.last_update_at = datetime.now(timezone.utc)
        else:
            # Create new
            progress = CheckProgress(
                check_id=check_id,
                followers_cursor=followers_cursor,
                following_cursor=following_cursor,
                followers_fetched=followers_fetched,
                following_fetched=following_fetched,
                followers_data=followers_data,
                following_data=following_data,
                status=status,
            )
            session.add(progress)
        
        await session.commit()
        await session.refresh(progress)
        
        logger.debug(
            f"Saved progress for check {check_id}: "
            f"followers={followers_fetched}, following={following_fetched}"
        )
        
        return progress


async def get_progress(check_id: uuid.UUID) -> CheckProgress | None:
    """Get check progress from database.
    
    Args:
        check_id: Check UUID.
        
    Returns:
        CheckProgress or None if not found.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(CheckProgress)
            .where(CheckProgress.check_id == check_id)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def mark_progress_paused(check_id: uuid.UUID) -> bool:
    """Mark check progress as paused (for later resumption).
    
    Args:
        check_id: Check UUID.
        
    Returns:
        True if progress was updated, False if not found.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            update(CheckProgress)
            .where(CheckProgress.check_id == check_id)
            .values(
                status=CheckProgressStatusEnum.PAUSED,
                last_update_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        
        if result.rowcount > 0:
            logger.info(f"Marked progress as paused for check {check_id}")
            return True
        return False


async def mark_progress_completed(check_id: uuid.UUID) -> bool:
    """Mark check progress as completed.
    
    Args:
        check_id: Check UUID.
        
    Returns:
        True if progress was updated, False if not found.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            update(CheckProgress)
            .where(CheckProgress.check_id == check_id)
            .values(
                status=CheckProgressStatusEnum.COMPLETED,
                last_update_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        
        return result.rowcount > 0


async def mark_progress_failed(check_id: uuid.UUID) -> bool:
    """Mark check progress as failed.
    
    Args:
        check_id: Check UUID.
        
    Returns:
        True if progress was updated, False if not found.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            update(CheckProgress)
            .where(CheckProgress.check_id == check_id)
            .values(
                status=CheckProgressStatusEnum.FAILED,
                last_update_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        
        return result.rowcount > 0


async def delete_progress(check_id: uuid.UUID) -> bool:
    """Delete check progress record.
    
    Called when check completes successfully or is cleaned up.
    
    Args:
        check_id: Check UUID.
        
    Returns:
        True if progress was deleted, False if not found.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            delete(CheckProgress)
            .where(CheckProgress.check_id == check_id)
        )
        await session.commit()
        
        return result.rowcount > 0


async def get_paused_checks() -> list[CheckProgress]:
    """Get all paused checks that can be resumed.
    
    Returns:
        List of CheckProgress records with status PAUSED.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(CheckProgress)
            .where(CheckProgress.status == CheckProgressStatusEnum.PAUSED)
            .order_by(CheckProgress.last_update_at.asc())
        )
        return list(result.scalars().all())


async def cleanup_old_progress(days: int = 7) -> int:
    """Clean up old progress records.
    
    Removes progress records older than specified days that are
    either completed or failed.
    
    Args:
        days: Age threshold in days.
        
    Returns:
        Number of records deleted.
    """
    from datetime import timedelta
    
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    
    async with async_session_maker() as session:
        result = await session.execute(
            delete(CheckProgress)
            .where(CheckProgress.last_update_at < threshold)
            .where(CheckProgress.status.in_([
                CheckProgressStatusEnum.COMPLETED,
                CheckProgressStatusEnum.FAILED,
            ]))
        )
        await session.commit()
        
        count = result.rowcount
        if count > 0:
            logger.info(f"Cleaned up {count} old progress records")
        
        return count
