"""Instagram session management service.

Handles persistent storage of Instagram session IDs in the database,
validation of session tokens, and fallback logic.
"""

from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from app.models.database import async_session_maker
from app.models.models import InstagramSession
from app.utils.logger import logger


# Cache for sync access (updated by async functions)
_cached_session_id: str | None = None
_cache_timestamp: datetime | None = None
CACHE_TTL_SECONDS = 60  # Refresh cache every minute


async def get_active_session_id() -> str | None:
    """Get the currently active session ID from the database.
    
    Returns:
        The active session ID or None if not found.
    """
    global _cached_session_id, _cache_timestamp
    
    async with async_session_maker() as session:
        result = await session.execute(
            select(InstagramSession)
            .where(InstagramSession.is_active == True)
            .where(InstagramSession.is_valid == True)
            .order_by(InstagramSession.created_at.desc())
            .limit(1)
        )
        ig_session = result.scalar_one_or_none()
        
        if ig_session:
            # Update cache
            _cached_session_id = ig_session.session_id
            _cache_timestamp = datetime.now(timezone.utc)
            return ig_session.session_id
        
        return None


def get_active_session_id_sync() -> str | None:
    """Get cached session ID for synchronous access.
    
    This uses a cached value that is periodically updated by async functions.
    Useful for config.py which needs sync access.
    
    Returns:
        Cached session ID or None.
    """
    global _cached_session_id, _cache_timestamp
    
    # Check if cache is still valid
    if _cached_session_id and _cache_timestamp:
        age = (datetime.now(timezone.utc) - _cache_timestamp).total_seconds()
        if age < CACHE_TTL_SECONDS:
            return _cached_session_id
    
    return _cached_session_id  # Return even stale cache, async will refresh


async def save_session_id(session_id: str, notes: str | None = None) -> InstagramSession:
    """Save a new session ID to the database.
    
    This deactivates all previous sessions and creates a new active one.
    
    Args:
        session_id: The Instagram session ID to save.
        notes: Optional notes about this session.
        
    Returns:
        The created InstagramSession record.
    """
    global _cached_session_id, _cache_timestamp
    
    async with async_session_maker() as session:
        # Deactivate all existing sessions
        await session.execute(
            update(InstagramSession)
            .where(InstagramSession.is_active == True)
            .values(is_active=False)
        )
        
        # Create new session
        new_session = InstagramSession(
            session_id=session_id,
            is_active=True,
            is_valid=True,
            notes=notes,
            last_verified_at=datetime.now(timezone.utc),
        )
        session.add(new_session)
        await session.commit()
        await session.refresh(new_session)
        
        # Update cache
        _cached_session_id = session_id
        _cache_timestamp = datetime.now(timezone.utc)
        
        logger.info(f"Saved new Instagram session (ID: {new_session.id})")
        return new_session


async def validate_session_id(session_id: str) -> tuple[bool, str]:
    """Validate an Instagram session ID by making a test API request.
    
    Makes a request to Instagram's web profile API to check if the session
    is valid and authenticated.
    
    Args:
        session_id: The session ID to validate.
        
    Returns:
        Tuple of (is_valid, message).
    """
    test_url = "https://www.instagram.com/api/v1/users/web_profile_info/"
    params = {"username": "instagram"}  # Official Instagram account (always exists)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
        "Origin": "https://www.instagram.com",
    }
    
    cookies = {
        "sessionid": session_id,
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                test_url,
                params=params,
                headers=headers,
                cookies=cookies,
            )
            
            if response.status_code == 200:
                data = response.json()
                user = data.get("data", {}).get("user")
                if user and user.get("username") == "instagram":
                    logger.info("Session ID validation successful")
                    return True, "Session is valid and authenticated"
                else:
                    logger.warning("Session validation: unexpected response structure")
                    return False, "Invalid response from Instagram"
                    
            elif response.status_code == 401:
                logger.warning("Session ID validation failed: unauthorized")
                return False, "Session expired or invalid (401 Unauthorized)"
                
            elif response.status_code == 429:
                logger.warning("Session validation: rate limited")
                # Don't reject the token just because of rate limiting
                return True, "Rate limited, but session may be valid"
                
            else:
                logger.warning(f"Session validation: unexpected status {response.status_code}")
                return False, f"Unexpected response: {response.status_code}"
                
    except httpx.TimeoutException:
        logger.error("Session validation: timeout")
        return False, "Request timed out"
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return False, f"Validation error: {str(e)}"


async def mark_session_invalid(session_id: str | None = None) -> bool:
    """Mark a session as invalid (usually due to expiration).
    
    Args:
        session_id: The session ID to mark invalid. If None, marks the active session.
        
    Returns:
        True if a session was marked invalid, False otherwise.
    """
    global _cached_session_id
    
    async with async_session_maker() as session:
        if session_id:
            result = await session.execute(
                update(InstagramSession)
                .where(InstagramSession.session_id == session_id)
                .values(is_valid=False)
            )
        else:
            result = await session.execute(
                update(InstagramSession)
                .where(InstagramSession.is_active == True)
                .values(is_valid=False)
            )
        
        await session.commit()
        
        if result.rowcount > 0:
            _cached_session_id = None  # Clear cache
            logger.warning(f"Marked session(s) as invalid (count: {result.rowcount})")
            return True
        
        return False


async def update_session_last_used(session_id: str) -> None:
    """Update the last_used_at timestamp for a session.
    
    Args:
        session_id: The session ID to update.
    """
    async with async_session_maker() as session:
        await session.execute(
            update(InstagramSession)
            .where(InstagramSession.session_id == session_id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        await session.commit()


async def get_session_info() -> dict | None:
    """Get information about the current active session.
    
    Returns:
        Dict with session info or None if no active session.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(InstagramSession)
            .where(InstagramSession.is_active == True)
            .order_by(InstagramSession.created_at.desc())
            .limit(1)
        )
        ig_session = result.scalar_one_or_none()
        
        if not ig_session:
            return None
        
        # Mask session ID for security
        masked = ig_session.session_id[:8] + "..." + ig_session.session_id[-4:] \
            if len(ig_session.session_id) > 12 else "***"
        
        return {
            "id": ig_session.id,
            "session_id_masked": masked,
            "is_active": ig_session.is_active,
            "is_valid": ig_session.is_valid,
            "created_at": ig_session.created_at.isoformat() if ig_session.created_at else None,
            "last_used_at": ig_session.last_used_at.isoformat() if ig_session.last_used_at else None,
            "last_verified_at": ig_session.last_verified_at.isoformat() if ig_session.last_verified_at else None,
            "notes": ig_session.notes,
        }


async def get_all_sessions() -> list[dict]:
    """Get all sessions (for admin listing).
    
    Returns:
        List of session info dicts.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(InstagramSession)
            .order_by(InstagramSession.created_at.desc())
            .limit(10)  # Last 10 sessions
        )
        sessions = result.scalars().all()
        
        return [
            {
                "id": s.id,
                "session_id_masked": s.session_id[:8] + "..." if len(s.session_id) > 8 else "***",
                "is_active": s.is_active,
                "is_valid": s.is_valid,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "notes": s.notes,
            }
            for s in sessions
        ]


async def refresh_session_cache() -> None:
    """Refresh the session cache from database.
    
    Call this periodically or after database changes.
    """
    await get_active_session_id()

