"""FastAPI router for tariff endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.database import get_session
from app.models.models import Tariff
from app.models.schemas import (
    TariffCreate,
    TariffListResponse,
    TariffResponse,
    TariffUpdate,
)
from app.utils.logger import logger

router = APIRouter(prefix="/tariffs", tags=["tariffs"])
settings = get_settings()


def verify_admin(x_user_id: Annotated[str | None, Header()] = None):
    """Verify the request is from an admin user."""
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User ID header required",
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


@router.get("", response_model=TariffListResponse)
async def get_tariffs(
    session: Annotated[AsyncSession, Depends(get_session)],
    include_inactive: bool = False,
):
    """Get all available tariffs."""
    query = select(Tariff)
    
    if not include_inactive:
        query = query.where(Tariff.is_active == True)
    
    query = query.order_by(Tariff.sort_order.asc(), Tariff.price_rub.asc())
    
    result = await session.execute(query)
    tariffs = result.scalars().all()

    return TariffListResponse(
        tariffs=[
            TariffResponse(
                tariff_id=t.tariff_id,
                name=t.name,
                description=t.description,
                checks_count=t.checks_count,
                price_rub=t.price_rub,
                price_stars=t.price_stars,
                is_active=t.is_active,
                sort_order=t.sort_order,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in tariffs
        ],
        total=len(tariffs),
    )


@router.get("/{tariff_id}", response_model=TariffResponse)
async def get_tariff(
    tariff_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a specific tariff by ID."""
    result = await session.execute(
        select(Tariff).where(Tariff.tariff_id == tariff_id)
    )
    tariff = result.scalar_one_or_none()

    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tariff {tariff_id} not found",
        )

    return TariffResponse(
        tariff_id=tariff.tariff_id,
        name=tariff.name,
        description=tariff.description,
        checks_count=tariff.checks_count,
        price_rub=tariff.price_rub,
        price_stars=tariff.price_stars,
        is_active=tariff.is_active,
        sort_order=tariff.sort_order,
        created_at=tariff.created_at,
        updated_at=tariff.updated_at,
    )


# --- Admin Endpoints ---


@router.post("/admin", response_model=TariffResponse)
async def create_tariff(
    tariff_data: TariffCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
):
    """Create a new tariff (admin only)."""
    tariff = Tariff(
        name=tariff_data.name,
        description=tariff_data.description,
        checks_count=tariff_data.checks_count,
        price_rub=tariff_data.price_rub,
        price_stars=tariff_data.price_stars,
        is_active=tariff_data.is_active,
        sort_order=tariff_data.sort_order,
    )
    session.add(tariff)
    await session.commit()
    await session.refresh(tariff)

    logger.info(f"Admin {admin_id} created tariff: {tariff.name} (ID: {tariff.tariff_id})")

    return TariffResponse(
        tariff_id=tariff.tariff_id,
        name=tariff.name,
        description=tariff.description,
        checks_count=tariff.checks_count,
        price_rub=tariff.price_rub,
        price_stars=tariff.price_stars,
        is_active=tariff.is_active,
        sort_order=tariff.sort_order,
        created_at=tariff.created_at,
        updated_at=tariff.updated_at,
    )


@router.put("/admin/{tariff_id}", response_model=TariffResponse)
async def update_tariff(
    tariff_id: uuid.UUID,
    tariff_data: TariffUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
):
    """Update an existing tariff (admin only)."""
    result = await session.execute(
        select(Tariff).where(Tariff.tariff_id == tariff_id)
    )
    tariff = result.scalar_one_or_none()

    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tariff {tariff_id} not found",
        )

    # Update only provided fields
    update_data = tariff_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tariff, field, value)

    await session.commit()
    await session.refresh(tariff)

    logger.info(f"Admin {admin_id} updated tariff {tariff_id}: {update_data}")

    return TariffResponse(
        tariff_id=tariff.tariff_id,
        name=tariff.name,
        description=tariff.description,
        checks_count=tariff.checks_count,
        price_rub=tariff.price_rub,
        price_stars=tariff.price_stars,
        is_active=tariff.is_active,
        sort_order=tariff.sort_order,
        created_at=tariff.created_at,
        updated_at=tariff.updated_at,
    )


@router.delete("/admin/{tariff_id}")
async def deactivate_tariff(
    tariff_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    admin_id: int = Depends(verify_admin),
):
    """Deactivate a tariff (admin only). Does not delete, just sets is_active=False."""
    result = await session.execute(
        select(Tariff).where(Tariff.tariff_id == tariff_id)
    )
    tariff = result.scalar_one_or_none()

    if not tariff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tariff {tariff_id} not found",
        )

    tariff.is_active = False
    await session.commit()

    logger.info(f"Admin {admin_id} deactivated tariff {tariff_id}")

    return {"message": f"Tariff {tariff_id} deactivated", "tariff_id": str(tariff_id)}

