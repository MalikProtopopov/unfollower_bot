"""FastAPI router for referral endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.models.schemas import (
    ReferralListResponse,
    ReferralRegisterRequest,
    ReferralRegisterResponse,
    ReferralStatsResponse,
)
from app.services.referral_service import (
    get_referral_list,
    get_referral_stats,
    register_referral,
)
from app.utils.logger import logger

router = APIRouter(prefix="/referrals", tags=["referrals"])


@router.get("/stats", response_model=ReferralStatsResponse)
async def get_stats(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get referral statistics for a user."""
    stats = await get_referral_stats(user_id)
    
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    
    return ReferralStatsResponse(**stats)


@router.get("/list", response_model=ReferralListResponse)
async def get_list(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 20,
    offset: int = 0,
):
    """Get list of referrals made by a user."""
    result = await get_referral_list(user_id, limit, offset)
    
    return ReferralListResponse(
        referrals=[
            {
                "referred_user_id": r["referred_user_id"],
                "referred_username": r["referred_username"],
                "created_at": r["created_at"],
                "bonus_granted": r["bonus_granted"],
            }
            for r in result["referrals"]
        ],
        total=result["total"],
    )


@router.post("/register", response_model=ReferralRegisterResponse)
async def register(
    request: ReferralRegisterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Register a new referral relationship.
    
    Called when a new user joins using a referral link.
    """
    result = await register_referral(request.referrer_code, request.referred_user_id)
    
    logger.info(
        f"Referral registration: code={request.referrer_code}, "
        f"referred={request.referred_user_id}, result={result}"
    )
    
    return ReferralRegisterResponse(
        success=result["success"],
        message=result["message"],
        bonus_granted_to_referrer=result.get("bonus_granted_to_referrer", False),
    )

