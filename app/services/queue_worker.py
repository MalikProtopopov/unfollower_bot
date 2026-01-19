"""Queue worker for processing checks sequentially."""

import asyncio
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import get_settings
from app.services.check_service import process_check
from app.services.queue_service import (
    clear_stale_processing,
    get_next_in_queue,
    get_processing_count,
    get_queue_status,
)
from app.utils.logger import logger

settings = get_settings()


async def process_queue():
    """Process checks from the queue one by one."""
    logger.info("Queue worker started")
    
    cleanup_counter = 0
    
    while True:
        try:
            # Periodically clean up stale processing checks
            cleanup_counter += 1
            if cleanup_counter >= 60:  # Every ~5 minutes (60 * 5 sec interval)
                stale_count = await clear_stale_processing(timeout_minutes=30)
                if stale_count > 0:
                    logger.info(f"Cleaned up {stale_count} stale checks")
                cleanup_counter = 0
            
            # Check if we're already at max concurrent checks
            processing_count = await get_processing_count()
            if processing_count >= settings.max_concurrent_checks:
                logger.debug(
                    f"Max concurrent checks reached ({processing_count}/{settings.max_concurrent_checks}), "
                    "waiting..."
                )
                await asyncio.sleep(settings.queue_processing_interval)
                continue
            
            # Get next check from queue
            check = await get_next_in_queue()
            
            if check is None:
                # No pending checks, wait
                await asyncio.sleep(settings.queue_processing_interval)
                continue
            
            # Log queue status
            status = await get_queue_status()
            logger.info(
                f"Processing check {check.check_id} for @{check.target_username}. "
                f"Queue: {status['total_pending']} pending, {status['total_processing']} processing"
            )
            
            # Process the check
            try:
                await process_check(str(check.check_id))
            except Exception as e:
                logger.exception(f"Error processing check {check.check_id}: {e}")
            
            # Small delay before next check
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.exception(f"Queue worker error: {e}")
            await asyncio.sleep(settings.queue_processing_interval)


async def main():
    """Main entry point for the queue worker."""
    logger.info("=" * 50)
    logger.info("Starting Check Queue Worker")
    logger.info(f"Max concurrent checks: {settings.max_concurrent_checks}")
    logger.info(f"Processing interval: {settings.queue_processing_interval}s")
    logger.info("=" * 50)
    
    try:
        await process_queue()
    except KeyboardInterrupt:
        logger.info("Queue worker stopped by user")
    except Exception as e:
        logger.exception(f"Queue worker fatal error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

