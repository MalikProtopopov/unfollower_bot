"""TaskIQ worker for processing background tasks.

Run with: python -m app.tasks.worker
Or use taskiq CLI: taskiq worker app.tasks:broker
"""

import asyncio

from app.tasks.broker import broker
from app.utils.logger import logger


async def main():
    """Main entry point for worker."""
    logger.info("Starting TaskIQ worker")
    
    # Import tasks to register them with the broker
    from app.tasks import session_tasks  # noqa: F401
    
    # Start the broker
    await broker.startup()
    
    logger.info("Worker is ready to process tasks")
    
    try:
        # Keep the worker running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
