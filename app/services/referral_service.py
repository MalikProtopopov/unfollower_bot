"""Referral service for managing referral program."""

from sqlalchemy import func, select

from app.config import get_settings
from app.models.database import async_session_maker
from app.models.models import Referral, User
from app.services.notification_service import notify_new_referral, notify_referral_bonus
from app.utils.logger import logger

settings = get_settings()


async def register_referral(referrer_code: str, referred_user_id: int) -> dict:
    """Register a new referral relationship.
    
    Args:
        referrer_code: The referral code of the referrer
        referred_user_id: The user ID of the new user who was referred
        
    Returns:
        Dictionary with registration result
    """
    async with async_session_maker() as session:
        # Find the referrer by their referral code
        referrer_result = await session.execute(
            select(User).where(User.referral_code == referrer_code)
        )
        referrer = referrer_result.scalar_one_or_none()
        
        if not referrer:
            logger.warning(f"Referrer not found for code: {referrer_code}")
            return {"success": False, "message": "Referrer not found"}
        
        # Can't refer yourself
        if referrer.user_id == referred_user_id:
            logger.warning(f"User {referred_user_id} tried to refer themselves")
            return {"success": False, "message": "Cannot refer yourself"}
        
        # Check if this user was already referred
        existing_referral = await session.execute(
            select(Referral).where(Referral.referred_user_id == referred_user_id)
        )
        if existing_referral.scalar_one_or_none():
            logger.info(f"User {referred_user_id} was already referred")
            return {"success": False, "message": "User already has a referrer"}
        
        # Create referral record
        referral = Referral(
            referrer_user_id=referrer.user_id,
            referred_user_id=referred_user_id,
            bonus_granted=False,
        )
        session.add(referral)
        
        # Update the referred user's referrer_id
        referred_result = await session.execute(
            select(User).where(User.user_id == referred_user_id)
        )
        referred_user = referred_result.scalar_one_or_none()
        if referred_user:
            referred_user.referrer_id = referrer.user_id
        
        await session.commit()
        
        logger.info(
            f"Referral registered: {referrer.user_id} -> {referred_user_id} "
            f"(code: {referrer_code})"
        )
        
        # Notify referrer about new referral
        await notify_new_referral(
            referrer.user_id, 
            referred_user.username if referred_user else None
        )
        
        # Check if referrer should receive a bonus
        bonus_granted = await check_and_grant_bonus(referrer.user_id)
        
        return {
            "success": True,
            "message": "Referral registered successfully",
            "bonus_granted_to_referrer": bonus_granted,
        }


async def check_and_grant_bonus(referrer_user_id: int) -> bool:
    """Check if referrer has earned a bonus and grant it.
    
    Grants one free check for every REFERRAL_REQUIRED_COUNT referrals.
    
    Args:
        referrer_user_id: The user ID of the referrer
        
    Returns:
        True if bonus was granted, False otherwise
    """
    async with async_session_maker() as session:
        # Count total referrals for this user
        total_result = await session.execute(
            select(func.count(Referral.referral_id))
            .where(Referral.referrer_user_id == referrer_user_id)
        )
        total_referrals = total_result.scalar() or 0
        
        # Count referrals that already granted bonuses
        bonus_granted_result = await session.execute(
            select(func.count(Referral.referral_id))
            .where(Referral.referrer_user_id == referrer_user_id)
            .where(Referral.bonus_granted == True)
        )
        bonus_granted_count = bonus_granted_result.scalar() or 0
        
        # Calculate how many bonuses should have been granted
        required_count = settings.referral_required_count
        expected_bonuses = total_referrals // required_count
        
        if expected_bonuses > bonus_granted_count:
            # Grant bonus
            user_result = await session.execute(
                select(User).where(User.user_id == referrer_user_id)
            )
            user = user_result.scalar_one_or_none()
            
            if user:
                bonus_checks = settings.referral_bonus_checks
                user.checks_balance += bonus_checks
                
                # Mark the required number of referrals as bonus_granted
                # Get the oldest referrals that haven't granted bonus yet
                referrals_to_mark = await session.execute(
                    select(Referral)
                    .where(Referral.referrer_user_id == referrer_user_id)
                    .where(Referral.bonus_granted == False)
                    .order_by(Referral.created_at.asc())
                    .limit(required_count)
                )
                for ref in referrals_to_mark.scalars().all():
                    ref.bonus_granted = True
                
                await session.commit()
                
                logger.info(
                    f"Granted {bonus_checks} bonus checks to user {referrer_user_id} "
                    f"for reaching {total_referrals} referrals"
                )
                
                # Notify user about the bonus
                await notify_referral_bonus(referrer_user_id, bonus_checks)
                
                return True
        
        return False


async def get_referral_stats(user_id: int) -> dict:
    """Get referral statistics for a user.
    
    Args:
        user_id: The user ID to get stats for
        
    Returns:
        Dictionary with referral statistics
    """
    async with async_session_maker() as session:
        # Get user
        user_result = await session.execute(
            select(User).where(User.user_id == user_id)
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.warning(f"User {user_id} not found in get_referral_stats")
            return None
        
        logger.info(f"Getting referral stats for user {user_id}, referral_code: {user.referral_code}")
        
        # Count total referrals
        total_result = await session.execute(
            select(func.count(Referral.referral_id))
            .where(Referral.referrer_user_id == user_id)
        )
        total_referrals = total_result.scalar() or 0
        
        # Also check raw count for debugging
        raw_count_result = await session.execute(
            select(Referral).where(Referral.referrer_user_id == user_id)
        )
        raw_referrals = raw_count_result.scalars().all()
        logger.info(
            f"User {user_id} referral count: total_referrals={total_referrals}, "
            f"raw_count={len(raw_referrals)}, referral_ids={[r.referral_id for r in raw_referrals]}"
        )
        
        # Calculate progress
        required_count = settings.referral_required_count
        bonus_progress = total_referrals % required_count
        referrals_for_bonus = required_count - bonus_progress
        total_bonuses = total_referrals // required_count
        
        # Generate referral link
        bot_username = settings.bot_username or "your_bot"
        referral_code = user.referral_code or f"ref_{user_id}"
        referral_link = f"https://t.me/{bot_username}?start={referral_code}"
        
        result = {
            "user_id": user_id,
            "referral_code": referral_code,
            "referral_link": referral_link,
            "total_referrals": total_referrals,
            "referrals_for_bonus": referrals_for_bonus,
            "bonus_progress": bonus_progress,
            "total_bonuses_earned": total_bonuses,
        }
        
        logger.info(f"Returning referral stats for user {user_id}: {result}")
        
        return result


async def get_referral_list(user_id: int, limit: int = 20, offset: int = 0) -> dict:
    """Get list of referrals made by a user.
    
    Args:
        user_id: The user ID to get referrals for
        limit: Maximum number of referrals to return
        offset: Number of referrals to skip
        
    Returns:
        Dictionary with referral list
    """
    async with async_session_maker() as session:
        # Get referrals with referred user info
        result = await session.execute(
            select(Referral, User)
            .join(User, Referral.referred_user_id == User.user_id)
            .where(Referral.referrer_user_id == user_id)
            .order_by(Referral.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        referrals = result.all()
        
        # Count total
        count_result = await session.execute(
            select(func.count(Referral.referral_id))
            .where(Referral.referrer_user_id == user_id)
        )
        total = count_result.scalar() or 0
        
        return {
            "referrals": [
                {
                    "referred_user_id": ref.referred_user_id,
                    "referred_username": user.username,
                    "created_at": ref.created_at,
                    "bonus_granted": ref.bonus_granted,
                }
                for ref, user in referrals
            ],
            "total": total,
        }

