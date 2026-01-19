"""FastAPI router for admin endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_instagram_session_id, get_settings, set_instagram_session_id
from app.models.database import get_session
from app.models.models import Check, CheckStatusEnum, Payment, PaymentStatusEnum, User
from app.utils.logger import logger

router = APIRouter(prefix="/admin", tags=["admin"])
settings = get_settings()


def verify_admin(x_user_id: Annotated[str | None, Header()] = None):
    """Verify the request is from an admin user."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-Id header required",
        )
    
    try:
        user_id = int(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format",
        )
    
    if not settings.is_admin(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    
    return user_id


# --- Session Management ---


class SessionUpdateRequest(BaseModel):
    """Request schema for updating Instagram session."""
    session_id: str


class SessionResponse(BaseModel):
    """Response schema for session info."""
    session_id_masked: str
    is_set: bool


@router.get("/session", response_model=SessionResponse)
async def get_session_status(admin_id: int = Depends(verify_admin)):
    """Get current Instagram session status (masked)."""
    session_id = get_instagram_session_id()
    
    if session_id:
        # Mask the session ID for security
        masked = session_id[:8] + "..." + session_id[-4:] if len(session_id) > 12 else "***"
    else:
        masked = "NOT SET"
    
    return SessionResponse(
        session_id_masked=masked,
        is_set=bool(session_id),
    )


@router.post("/session")
async def update_session(
    request: SessionUpdateRequest,
    admin_id: int = Depends(verify_admin),
):
    """Update Instagram session ID without server restart."""
    old_session = get_instagram_session_id()
    set_instagram_session_id(request.session_id)
    
    logger.info(f"Admin {admin_id} updated Instagram session ID")
    
    return {
        "message": "Session ID updated successfully",
        "old_session_masked": old_session[:8] + "..." if old_session else "NOT SET",
        "new_session_masked": request.session_id[:8] + "..." if request.session_id else "NOT SET",
    }


@router.delete("/session")
async def clear_session(admin_id: int = Depends(verify_admin)):
    """Clear Instagram session ID."""
    set_instagram_session_id("")
    
    logger.info(f"Admin {admin_id} cleared Instagram session ID")
    
    return {"message": "Session ID cleared"}


# --- Statistics ---


@router.get("/stats")
async def get_admin_stats(
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
):
    """Get admin statistics dashboard."""
    # Total users
    users_result = await session.execute(select(func.count(User.user_id)))
    total_users = users_result.scalar() or 0
    
    # Active users (with at least 1 check)
    active_users_result = await session.execute(
        select(func.count(func.distinct(Check.user_id)))
    )
    active_users = active_users_result.scalar() or 0
    
    # Total checks
    checks_result = await session.execute(select(func.count(Check.check_id)))
    total_checks = checks_result.scalar() or 0
    
    # Completed checks
    completed_result = await session.execute(
        select(func.count(Check.check_id))
        .where(Check.status == CheckStatusEnum.COMPLETED)
    )
    completed_checks = completed_result.scalar() or 0
    
    # Failed checks
    failed_result = await session.execute(
        select(func.count(Check.check_id))
        .where(Check.status == CheckStatusEnum.FAILED)
    )
    failed_checks = failed_result.scalar() or 0
    
    # Pending checks
    pending_result = await session.execute(
        select(func.count(Check.check_id))
        .where(Check.status.in_([CheckStatusEnum.PENDING, CheckStatusEnum.PROCESSING]))
    )
    pending_checks = pending_result.scalar() or 0
    
    # Total payments
    payments_result = await session.execute(
        select(func.count(Payment.payment_id))
        .where(Payment.status == PaymentStatusEnum.COMPLETED)
    )
    total_payments = payments_result.scalar() or 0
    
    # Total revenue
    revenue_result = await session.execute(
        select(func.sum(Payment.amount))
        .where(Payment.status == PaymentStatusEnum.COMPLETED)
    )
    total_revenue = float(revenue_result.scalar() or 0)
    
    # Session status
    session_id = get_instagram_session_id()
    session_status = "✅ Set" if session_id else "❌ Not set"
    
    return {
        "users": {
            "total": total_users,
            "active": active_users,
        },
        "checks": {
            "total": total_checks,
            "completed": completed_checks,
            "failed": failed_checks,
            "pending": pending_checks,
            "success_rate": round(completed_checks / total_checks * 100, 1) if total_checks else 0,
        },
        "payments": {
            "total_count": total_payments,
            "total_revenue": total_revenue,
        },
        "instagram": {
            "session_status": session_status,
        },
    }


# --- User Management ---


@router.get("/users")
async def get_users(
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
    limit: int = 50,
    offset: int = 0,
):
    """Get list of users."""
    result = await session.execute(
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    users = result.scalars().all()
    
    return {
        "users": [
            {
                "user_id": u.user_id,
                "username": u.username,
                "first_name": u.first_name,
                "checks_balance": u.checks_balance,
                "created_at": u.created_at,
            }
            for u in users
        ],
        "count": len(users),
    }


@router.post("/users/{user_id}/add-balance")
async def add_user_balance_admin(
    user_id: int,
    checks_count: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
):
    """Add checks to a user's balance."""
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    
    user.checks_balance += checks_count
    await session.commit()
    
    logger.info(f"Admin {admin_id} added {checks_count} checks to user {user_id}")
    
    return {
        "user_id": user_id,
        "checks_added": checks_count,
        "new_balance": user.checks_balance,
    }

