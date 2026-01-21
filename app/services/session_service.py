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
        # Follow redirects to handle 302 responses
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(
                test_url,
                params=params,
                headers=headers,
                cookies=cookies,
            )
            
            # Check final URL after redirects
            final_url = str(response.url)
            
            # If redirected to login page - session is invalid
            if "login" in final_url.lower() or "accounts/login" in final_url:
                logger.warning("Session validation: redirected to login page - session invalid")
                return False, "Session expired (redirected to login)"
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    user = data.get("data", {}).get("user")
                    if user and user.get("username") == "instagram":
                        logger.info("Session ID validation successful")
                        return True, "Session is valid and authenticated"
                    elif user:
                        # Got some user data - session likely works
                        logger.info("Session validation: got user data, session valid")
                        return True, "Session is valid"
                    else:
                        # No user data but 200 OK - might still work
                        logger.warning("Session validation: 200 OK but unexpected structure")
                        return True, "Session appears valid (200 OK)"
                except Exception as e:
                    # JSON parsing failed but 200 - might still work
                    logger.warning(f"Session validation: JSON error but 200 status: {e}")
                    return True, "Session appears valid (200 OK)"
                    
            elif response.status_code == 401:
                logger.warning("Session ID validation failed: unauthorized")
                return False, "Session expired or invalid (401 Unauthorized)"
                
            elif response.status_code == 429:
                logger.warning("Session validation: rate limited")
                # Don't reject the token just because of rate limiting
                return True, "Rate limited, but session may be valid"
            
            elif response.status_code in (301, 302, 303, 307, 308):
                # Redirect not followed (shouldn't happen with follow_redirects=True)
                # But if we're here, treat non-login redirects as potentially valid
                logger.warning(f"Session validation: redirect {response.status_code}")
                return True, "Session may be valid (redirect response)"
                
            else:
                logger.warning(f"Session validation: unexpected status {response.status_code}")
                # Don't immediately reject - session might still work
                return True, f"Session saved (status {response.status_code}, will test on first check)"
                
    except httpx.TimeoutException:
        logger.error("Session validation: timeout")
        # Timeout doesn't mean invalid - save anyway
        return True, "Validation timed out, but session saved"
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        # Save anyway and let it fail on actual use if invalid
        return True, f"Validation error ({str(e)}), but session saved"


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
            # Auto-refresh fields
            "next_refresh_at": ig_session.next_refresh_at.isoformat() if hasattr(ig_session, 'next_refresh_at') and ig_session.next_refresh_at else None,
            "fail_count": getattr(ig_session, 'fail_count', 0),
            "last_error": getattr(ig_session, 'last_error', None),
            "refresh_attempts": getattr(ig_session, 'refresh_attempts', 0),
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

