"""TaskIQ tasks for Instagram session management.

Tasks:
- proactive_refresh_task: Scheduled task to refresh session before expiry
- reactive_refresh_task: Triggered task when 401 error occurs
- check_session_health_task: Periodic health check of current session
"""

from datetime import datetime, timezone

from app.tasks.broker import broker
from app.services.session_refresh_service import get_refresh_service
from app.services.session_service import get_active_session_id, validate_session_id
from app.services.admin_notification_service import notify_admin_session_error
from app.utils.logger import logger


@broker.task
async def proactive_refresh_task() -> dict:
    """Proactively refresh Instagram session if needed.
    
    This task runs periodically (every 6 hours) to check if
    the session needs refreshing (age > 2 days).
    
    Returns:
        Dict with status and message.
    """
    logger.info("Running proactive refresh task")
    
    refresh_service = get_refresh_service()
    
    try:
        # Check if refresh is needed
        needs_refresh = await refresh_service.should_refresh_proactively()
        
        if not needs_refresh:
            logger.info("Proactive refresh not needed - session is still fresh")
            return {
                "status": "skipped",
                "message": "Session is still fresh",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        logger.info("Proactive refresh needed - starting refresh")
        
        # Perform refresh
        success, message = await refresh_service.refresh_session()
        
        if success:
            logger.info(f"Proactive refresh successful: {message}")
            return {
                "status": "success",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            logger.error(f"Proactive refresh failed: {message}")
            return {
                "status": "failed",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
    except Exception as e:
        logger.exception(f"Proactive refresh task error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await refresh_service.close()


@broker.task
async def reactive_refresh_task() -> dict:
    """Reactively refresh Instagram session after 401 error.
    
    This task is triggered when a 401 error is encountered during
    Instagram API requests. It immediately attempts to get a new session.
    
    Returns:
        Dict with status and message.
    """
    logger.info("Running reactive refresh task (triggered by 401 error)")
    
    refresh_service = get_refresh_service()
    
    try:
        success, message = await refresh_service.reactive_refresh()
        
        if success:
            logger.info(f"Reactive refresh successful: {message}")
            return {
                "status": "success",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            logger.error(f"Reactive refresh failed: {message}")
            # Notify admin on failure
            await notify_admin_session_error()
            return {
                "status": "failed",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
    except Exception as e:
        logger.exception(f"Reactive refresh task error: {e}")
        await notify_admin_session_error()
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await refresh_service.close()


@broker.task
async def check_session_health_task() -> dict:
    """Check health of current Instagram session.
    
    This task runs periodically to validate the current session
    and detect issues before they cause failures.
    
    Returns:
        Dict with session health status.
    """
    logger.info("Running session health check")
    
    try:
        # Get current session
        session_id = await get_active_session_id()
        
        if not session_id:
            logger.warning("No active session found")
            return {
                "status": "no_session",
                "message": "No active session configured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        # Validate session
        is_valid, message = await validate_session_id(session_id)
        
        if is_valid:
            logger.info(f"Session health check passed: {message}")
            return {
                "status": "healthy",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            logger.warning(f"Session health check failed: {message}")
            
            # Trigger reactive refresh
            logger.info("Triggering reactive refresh due to unhealthy session")
            await reactive_refresh_task.kiq()
            
            return {
                "status": "unhealthy",
                "message": message,
                "refresh_triggered": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
    except Exception as e:
        logger.exception(f"Session health check error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@broker.task
async def manual_refresh_task() -> dict:
    """Manually trigger session refresh.
    
    This task can be triggered via admin API to force a session refresh.
    
    Returns:
        Dict with status and message.
    """
    logger.info("Running manual refresh task (admin triggered)")
    
    refresh_service = get_refresh_service()
    
    try:
        success, message = await refresh_service.refresh_session()
        
        if success:
            logger.info(f"Manual refresh successful: {message}")
            return {
                "status": "success",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        else:
            logger.error(f"Manual refresh failed: {message}")
            return {
                "status": "failed",
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
    except Exception as e:
        logger.exception(f"Manual refresh task error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        await refresh_service.close()
