"""Queue service for managing check processing order."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.models.database import async_session_maker
from app.models.models import Check, CheckStatusEnum
from app.utils.logger import logger


async def add_to_queue(check_id: str) -> int:
    """Add a check to the processing queue.
    
    Args:
        check_id: The check UUID string
        
    Returns:
        The queue position assigned to this check
    """
    async with async_session_maker() as session:
        # Get the current max queue position
        result = await session.execute(
            select(func.max(Check.queue_position))
            .where(Check.status.in_([CheckStatusEnum.PENDING, CheckStatusEnum.PROCESSING]))
        )
        max_position = result.scalar() or 0
        new_position = max_position + 1
        
        # Update the check with queue position
        await session.execute(
            update(Check)
            .where(Check.check_id == uuid.UUID(check_id))
            .values(queue_position=new_position)
        )
        await session.commit()
        
        logger.info(f"Check {check_id} added to queue at position {new_position}")
        return new_position


async def get_next_in_queue() -> Check | None:
    """Get the next check to process from the queue.
    
    Returns:
        The next Check object to process, or None if queue is empty
    """
    async with async_session_maker() as session:
        # Get the check with lowest queue position that is pending
        result = await session.execute(
            select(Check)
            .where(Check.status == CheckStatusEnum.PENDING)
            .where(Check.queue_position.isnot(None))
            .order_by(Check.queue_position.asc())
            .limit(1)
        )
        check = result.scalar_one_or_none()
        
        if check:
            # Mark as processing
            check.status = CheckStatusEnum.PROCESSING
            check.started_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(check)
            logger.info(f"Check {check.check_id} taken from queue for processing")
            
        return check


async def get_processing_count() -> int:
    """Get count of currently processing checks.
    
    Returns:
        Number of checks currently being processed
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count(Check.check_id))
            .where(Check.status == CheckStatusEnum.PROCESSING)
        )
        return result.scalar() or 0


async def get_pending_count() -> int:
    """Get count of pending checks in queue.
    
    Returns:
        Number of checks waiting in queue
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(func.count(Check.check_id))
            .where(Check.status == CheckStatusEnum.PENDING)
        )
        return result.scalar() or 0


async def get_queue_position(check_id: str) -> int | None:
    """Get the current queue position for a check.
    
    Args:
        check_id: The check UUID string
        
    Returns:
        Queue position or None if not in queue
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(Check.queue_position)
            .where(Check.check_id == uuid.UUID(check_id))
        )
        return result.scalar_one_or_none()


async def update_queue_positions() -> None:
    """Recalculate queue positions to fill gaps.
    
    This should be called periodically to maintain clean queue positions.
    """
    async with async_session_maker() as session:
        # Get all pending checks ordered by current position
        result = await session.execute(
            select(Check)
            .where(Check.status == CheckStatusEnum.PENDING)
            .where(Check.queue_position.isnot(None))
            .order_by(Check.queue_position.asc())
        )
        checks = result.scalars().all()
        
        # Reassign positions sequentially
        for i, check in enumerate(checks, start=1):
            if check.queue_position != i:
                check.queue_position = i
        
        await session.commit()
        logger.debug(f"Queue positions updated for {len(checks)} checks")


async def get_queue_status() -> dict:
    """Get current queue status.
    
    Returns:
        Dictionary with queue statistics
    """
    pending = await get_pending_count()
    processing = await get_processing_count()
    
    # Estimate wait time (assuming ~2 min per check average)
    estimated_wait = (pending + processing) * 2
    
    return {
        "total_pending": pending,
        "total_processing": processing,
        "next_position": pending + processing + 1,
        "estimated_wait_minutes": estimated_wait,
    }


async def clear_stale_processing(timeout_minutes: int = 30) -> int:
    """Mark stale processing checks as failed.
    
    Checks that have been processing for longer than timeout are marked as failed.
    
    Args:
        timeout_minutes: Minutes after which a processing check is considered stale
        
    Returns:
        Number of checks marked as failed
    """
    async with async_session_maker() as session:
        threshold = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        
        result = await session.execute(
            select(Check)
            .where(Check.status == CheckStatusEnum.PROCESSING)
            .where(Check.started_at < threshold)
        )
        stale_checks = result.scalars().all()
        
        for check in stale_checks:
            check.status = CheckStatusEnum.FAILED
            check.error_message = "Проверка превысила максимальное время выполнения"
            logger.warning(f"Check {check.check_id} marked as failed due to timeout")
        
        await session.commit()
        return len(stale_checks)

