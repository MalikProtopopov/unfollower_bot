"""FastAPI router for check endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import get_session
from app.models.models import Check, CheckStatusEnum, NonMutualUser, PlatformEnum, User
from app.models.schemas import (
    CheckHistoryItem,
    CheckHistoryResponse,
    CheckInitiateRequest,
    CheckInitiateResponse,
    CheckStatus,
    CheckStatusResponse,
    NonMutualUserSchema,
    QueueStatusResponse,
    UserBalanceResponse,
)
from app.services.queue_service import add_to_queue, get_queue_status
from app.utils.logger import logger

router = APIRouter(tags=["checks"])


async def get_or_create_user(
    session: AsyncSession,
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Get existing user or create new one."""
    from app.config import get_settings
    settings = get_settings()
    
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        # Generate referral code from user_id
        referral_code = f"ref_{user_id}"
        
        # Admins get 100 free checks, regular users get 0
        initial_balance = 100 if settings.is_admin(user_id) else 0
        
        user = User(
            user_id=user_id,
            username=username,
            first_name=first_name,
            referral_code=referral_code,
            checks_balance=initial_balance,
        )
        session.add(user)
        await session.flush()
        logger.info(f"Created new user: {user_id} with referral_code: {referral_code}, balance: {initial_balance}")

    return user


@router.post("/check/initiate", response_model=CheckInitiateResponse)
async def initiate_check(
    request: CheckInitiateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Initiate a new followers check.

    Creates a check record and adds it to the processing queue.
    Requires user to have available checks balance.
    """
    # Ensure user exists
    user = await get_or_create_user(session, request.user_id)

    # Check balance
    if user.checks_balance <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="У вас нет доступных проверок. Пожалуйста, пополните баланс.",
        )

    # Deduct one check from balance
    user.checks_balance -= 1
    await session.flush()
    
    # Get queue status for position estimation
    queue_status = await get_queue_status()

    # Create check record
    check = Check(
        user_id=request.user_id,
        target_username=request.username,
        platform=PlatformEnum.INSTAGRAM,
        status=CheckStatusEnum.PENDING,
    )
    session.add(check)
    await session.commit()
    await session.refresh(check)

    logger.info(f"Created check {check.check_id} for @{request.username} (balance: {user.checks_balance})")

    # Add to processing queue
    queue_position = await add_to_queue(str(check.check_id))

    # Estimate time based on queue position
    estimated_time = 60 + (queue_position - 1) * 120  # Base 60s + 2min per position

    return CheckInitiateResponse(
        check_id=check.check_id,
        status=CheckStatus.PENDING,
        estimated_time=estimated_time,
        message=f"Проверка @{request.username} добавлена в очередь",
        queue_position=queue_position,
    )


@router.get("/check/{check_id}", response_model=CheckStatusResponse)
async def get_check_status(
    check_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get status of a check by ID."""
    result = await session.execute(
        select(Check).where(Check.check_id == check_id)
    )
    check = result.scalar_one_or_none()

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {check_id} not found",
        )

    # Build response
    response = CheckStatusResponse(
        check_id=check.check_id,
        status=CheckStatus(check.status.value),
        progress=check.progress,
        queue_position=check.queue_position,
        total_subscriptions=check.total_subscriptions,
        total_followers=check.total_followers,
        total_non_mutual=check.total_non_mutual,
        file_path=check.file_path,
        error_message=check.error_message,
        created_at=check.created_at,
        completed_at=check.completed_at,
    )

    # Add status message
    if check.status == CheckStatusEnum.PENDING:
        if check.queue_position:
            response.message = f"В очереди (позиция {check.queue_position})"
        else:
            response.message = "Check is queued for processing"
    elif check.status == CheckStatusEnum.PROCESSING:
        response.message = f"Processing... {check.progress}%"
    elif check.status == CheckStatusEnum.COMPLETED:
        response.message = "Check completed successfully"
    elif check.status == CheckStatusEnum.FAILED:
        response.message = check.error_message or "Check failed"

    # Include users list if completed
    if check.status == CheckStatusEnum.COMPLETED:
        users_result = await session.execute(
            select(NonMutualUser).where(NonMutualUser.check_id == check_id)
        )
        non_mutual_users = users_result.scalars().all()

        response.users = [
            NonMutualUserSchema(
                username=u.target_username,
                full_name=u.target_full_name,
                avatar_url=u.target_avatar_url,
                user_follows_target=u.user_follows_target,
                target_follows_user=u.target_follows_user,
                is_mutual=u.is_mutual,
            )
            for u in non_mutual_users
        ]

    return response


@router.get("/checks", response_model=CheckHistoryResponse)
async def get_user_checks(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 10,
    offset: int = 0,
):
    """Get check history for a user."""
    # Get total count
    count_result = await session.execute(
        select(Check).where(Check.user_id == user_id)
    )
    total = len(count_result.scalars().all())

    # Get paginated results
    result = await session.execute(
        select(Check)
        .where(Check.user_id == user_id)
        .order_by(Check.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    checks = result.scalars().all()

    return CheckHistoryResponse(
        checks=[
            CheckHistoryItem(
                check_id=c.check_id,
                target_username=c.target_username,
                platform=c.platform.value,
                status=CheckStatus(c.status.value),
                total_non_mutual=c.total_non_mutual,
                created_at=c.created_at,
                completed_at=c.completed_at,
            )
            for c in checks
        ],
        total=total,
    )


@router.get("/check/{check_id}/file")
async def get_check_file(
    check_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get file path for completed check."""
    result = await session.execute(
        select(Check).where(Check.check_id == check_id)
    )
    check = result.scalar_one_or_none()

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {check_id} not found",
        )

    if check.status != CheckStatusEnum.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check is not completed yet",
        )

    if not check.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found for this check",
        )

    return {"file_path": check.file_path}


# --- User Balance Endpoints ---


@router.post("/users/ensure", response_model=UserBalanceResponse)
async def ensure_user_exists(
    user_id: int,
    username: str | None = None,
    first_name: str | None = None,
    session: Annotated[AsyncSession, Depends(get_session)] = None,
):
    """Ensure user exists in the database (create if not exists)."""
    user = await get_or_create_user(session, user_id, username, first_name)
    await session.commit()
    
    return UserBalanceResponse(
        user_id=user.user_id,
        checks_balance=user.checks_balance,
        referral_code=user.referral_code,
    )


@router.get("/users/{user_id}/balance", response_model=UserBalanceResponse)
async def get_user_balance(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get user's check balance."""
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    logger.info(
        f"Balance request for user {user_id}: "
        f"checks_balance={user.checks_balance}, "
        f"referral_code={user.referral_code}"
    )

    return UserBalanceResponse(
        user_id=user.user_id,
        checks_balance=user.checks_balance,
        referral_code=user.referral_code,
    )


@router.post("/users/{user_id}/balance/add")
async def add_user_balance(
    user_id: int,
    checks_count: int,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Add checks to user's balance (admin endpoint)."""
    result = await session.execute(select(User).where(User.user_id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    user.checks_balance += checks_count
    await session.commit()

    logger.info(f"Added {checks_count} checks to user {user_id}. New balance: {user.checks_balance}")

    return {
        "user_id": user.user_id,
        "checks_added": checks_count,
        "new_balance": user.checks_balance,
    }


# --- Queue Status Endpoint ---


@router.get("/queue/status", response_model=QueueStatusResponse)
async def get_queue_status_endpoint():
    """Get current queue status."""
    status_data = await get_queue_status()
    return QueueStatusResponse(**status_data)
