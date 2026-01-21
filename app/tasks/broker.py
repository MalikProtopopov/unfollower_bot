"""TaskIQ broker configuration.

TaskIQ is a modern async task queue for Python.
We use Redis as the broker for distributed task execution.
"""

import os
from datetime import timedelta

from taskiq import InMemoryBroker
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker

from app.utils.logger import logger


# Get Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Check if Redis is available, otherwise use in-memory broker for development
USE_REDIS = os.getenv("USE_REDIS", "false").lower() == "true"

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


# Task schedule for periodic tasks
# Will be used by scheduler
TASK_SCHEDULES = {
    "proactive_refresh": {
        "task": "app.tasks.session_tasks:proactive_refresh_task",
        "schedule": timedelta(hours=6),  # Check every 6 hours if refresh needed
        "args": [],
    },
    "check_session_health": {
        "task": "app.tasks.session_tasks:check_session_health_task",
        "schedule": timedelta(hours=1),  # Check health every hour
        "args": [],
    },
}
