"""TaskIQ scheduler for periodic tasks.

This module runs the scheduler that triggers periodic tasks:
- Proactive session refresh (configurable, default 6 hours)
- Session health check (configurable, default 1 hour)

Run with: python -m app.tasks.scheduler
"""

import asyncio
from datetime import datetime, timezone

from app.config import get_settings
from app.tasks.broker import broker, get_task_schedules
from app.tasks.session_tasks import proactive_refresh_task, check_session_health_task
from app.utils.logger import logger


async def run_scheduler():
    """Run the task scheduler.
    
    This is a simple scheduler that runs periodic tasks at fixed intervals.
    For production, consider using a more robust scheduler like APScheduler.
    """
    settings = get_settings()
    task_schedules = get_task_schedules()
    
    logger.info("Starting TaskIQ scheduler")
    logger.info(f"Scheduled tasks: {list(task_schedules.keys())}")
    logger.info(f"Proactive refresh interval: {settings.proactive_check_hours} hours")
    logger.info(f"Health check interval: {settings.health_check_hours} hours")
    
    # Track last run times
    last_run = {
        "proactive_refresh": datetime.min.replace(tzinfo=timezone.utc),
        "check_session_health": datetime.min.replace(tzinfo=timezone.utc),
    }
    
    while True:
        now = datetime.now(timezone.utc)
        
        # Check proactive refresh
        if (now - last_run["proactive_refresh"]).total_seconds() >= task_schedules["proactive_refresh"]["schedule"].total_seconds():
            logger.info("Scheduling proactive_refresh_task")
            await proactive_refresh_task.kiq()
            last_run["proactive_refresh"] = now
        
        # Check session health
        if (now - last_run["check_session_health"]).total_seconds() >= task_schedules["check_session_health"]["schedule"].total_seconds():
            logger.info("Scheduling check_session_health_task")
            await check_session_health_task.kiq()
            last_run["check_session_health"] = now
        
        # Sleep for 1 minute before next check
        await asyncio.sleep(60)


async def main():
    """Main entry point for scheduler."""
    # Start the broker
    await broker.startup()
    
    try:
        await run_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
