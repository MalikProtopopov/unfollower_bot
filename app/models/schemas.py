"""Pydantic schemas for API request/response validation."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, field_validator

from app.utils.validators import validate_instagram_username


class PlatformType(str, Enum):
    """Supported platforms."""

    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"


class CheckStatus(str, Enum):
    """Check status values."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PaymentMethod(str, Enum):
    """Payment method values."""

    ROBOKASSA = "robokassa"
    TELEGRAM_STARS = "telegram_stars"
    MANUAL = "manual"


class PaymentStatus(str, Enum):
    """Payment status values."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# --- Request Schemas ---


class CheckInitiateRequest(BaseModel):
    """Request schema for initiating a check."""

    username: str = Field(..., min_length=1, max_length=30, description="Target username to check")
    platform: PlatformType = Field(default=PlatformType.INSTAGRAM, description="Platform type")
    user_id: int = Field(..., description="Telegram user ID")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate and normalize username."""
        # Remove @ prefix if present
        clean_username = v.strip().lstrip("@")
        if not validate_instagram_username(clean_username):
            raise ValueError("Invalid Instagram username format")
        return clean_username.lower()


# --- Response Schemas ---


class CheckInitiateResponse(BaseModel):
    """Response schema for check initiation."""

    check_id: uuid.UUID
    status: CheckStatus = CheckStatus.PENDING
    estimated_time: int = Field(default=60, description="Estimated time in seconds")
    message: str = Field(default="Check initiated successfully")
    queue_position: int | None = None


class NonMutualUserSchema(BaseModel):
    """Schema for non-mutual user data."""

    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    user_follows_target: bool = True
    target_follows_user: bool = False
    is_mutual: bool = False

    class Config:
        from_attributes = True


class CheckStatusResponse(BaseModel):
    """Response schema for check status."""

    check_id: uuid.UUID
    status: CheckStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str | None = None
    queue_position: int | None = None

    # Available when completed
    total_subscriptions: int | None = None
    total_followers: int | None = None
    total_non_mutual: int | None = None
    users: list[NonMutualUserSchema] | None = None
    file_path: str | None = None

    # Error info
    error_message: str | None = None

    # Timestamps
    created_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class CheckHistoryItem(BaseModel):
    """Schema for check history list item."""

    check_id: uuid.UUID
    target_username: str
    platform: PlatformType
    status: CheckStatus
    total_non_mutual: int | None = None
    created_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class CheckHistoryResponse(BaseModel):
    """Response schema for user's check history."""

    checks: list[CheckHistoryItem]
    total: int


# --- User & Balance Schemas ---


class UserBalanceResponse(BaseModel):
    """Response schema for user balance."""

    user_id: int
    checks_balance: int
    referral_code: str | None = None


class UserResponse(BaseModel):
    """Response schema for user info."""

    user_id: int
    username: str | None = None
    first_name: str | None = None
    checks_balance: int = 0
    referral_code: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# --- Tariff Schemas ---


class TariffBase(BaseModel):
    """Base schema for tariff."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    checks_count: int = Field(..., gt=0)
    price_rub: Decimal = Field(..., ge=0)
    price_stars: int | None = Field(default=None, ge=0)
    is_active: bool = True
    sort_order: int = 0


class TariffCreate(TariffBase):
    """Schema for creating a tariff."""

    pass


class TariffUpdate(BaseModel):
    """Schema for updating a tariff."""

    name: str | None = None
    description: str | None = None
    checks_count: int | None = Field(default=None, gt=0)
    price_rub: Decimal | None = Field(default=None, ge=0)
    price_stars: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    sort_order: int | None = None


class TariffResponse(TariffBase):
    """Response schema for tariff."""

    tariff_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TariffListResponse(BaseModel):
    """Response schema for tariff list."""

    tariffs: list[TariffResponse]
    total: int


# --- Payment Schemas ---


class PaymentCreateRequest(BaseModel):
    """Request schema for creating a payment."""

    user_id: int
    tariff_id: uuid.UUID
    payment_method: PaymentMethod


class PaymentResponse(BaseModel):
    """Response schema for payment."""

    payment_id: uuid.UUID
    user_id: int
    tariff_id: uuid.UUID | None = None
    amount: Decimal
    currency: str
    checks_count: int
    payment_method: PaymentMethod
    status: PaymentStatus
    robokassa_payment_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class RobokassaCallbackRequest(BaseModel):
    """Schema for Robokassa callback."""

    OutSum: str
    InvId: str
    SignatureValue: str
    # Optional fields
    Shp_user_id: int | None = None
    Shp_tariff_id: str | None = None


# --- Referral Schemas ---


class ReferralStatsResponse(BaseModel):
    """Response schema for referral statistics."""

    user_id: int
    referral_code: str
    referral_link: str
    total_referrals: int
    referrals_for_bonus: int  # How many needed for next bonus
    bonus_progress: int  # Current progress (0-9)
    total_bonuses_earned: int


class ReferralListItem(BaseModel):
    """Schema for referral list item."""

    referred_user_id: int
    referred_username: str | None = None
    created_at: datetime
    bonus_granted: bool

    class Config:
        from_attributes = True


class ReferralListResponse(BaseModel):
    """Response schema for referral list."""

    referrals: list[ReferralListItem]
    total: int


class ReferralRegisterRequest(BaseModel):
    """Request schema for registering a referral."""

    referrer_code: str
    referred_user_id: int


class ReferralRegisterResponse(BaseModel):
    """Response schema for referral registration."""

    success: bool
    message: str
    bonus_granted_to_referrer: bool = False


# --- Queue Schemas ---


class QueueStatusResponse(BaseModel):
    """Response schema for queue status."""

    total_pending: int
    total_processing: int
    next_position: int
    estimated_wait_minutes: int


# --- Error Schemas ---


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: str
    detail: str | None = None
    code: str | None = None
