"""TaskIQ broker configuration.

TaskIQ is a modern async task queue for Python.
We use Redis as the broker for distributed task execution.
"""

from datetime import timedelta

from taskiq import InMemoryBroker
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker

from app.config import get_settings
from app.utils.logger import logger


# Load settings
settings = get_settings()

# Get Redis URL from settings
REDIS_URL = settings.redis_url
USE_REDIS = settings.use_redis

if USE_REDIS:
    logger.info(f"Using Redis broker: {REDIS_URL}")
    broker = ListQueueBroker(
        url=REDIS_URL,
    ).with_result_backend(
        RedisAsyncResultBackend(
            redis_url=REDIS_URL,
        )
    )
else:
    logger.info("Using in-memory broker (for development)")
    broker = InMemoryBroker()


def get_task_schedules() -> dict:
    """Get task schedules with values from settings.
    
    Returns:
        Dict with task schedules.
    """
    settings = get_settings()
    return {
        "proactive_refresh": {
            "task": "app.tasks.session_tasks:proactive_refresh_task",
            "schedule": timedelta(hours=settings.proactive_check_hours),
            "args": [],
        },
        "check_session_health": {
            "task": "app.tasks.session_tasks:check_session_health_task",
            "schedule": timedelta(hours=settings.health_check_hours),
            "args": [],
        },
    }


# For backwards compatibility
TASK_SCHEDULES = get_task_schedules()
