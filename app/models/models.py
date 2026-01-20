"""SQLAlchemy database models."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.database import Base


class PlatformEnum(str, enum.Enum):
    """Supported social media platforms."""

    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"


class CheckStatusEnum(str, enum.Enum):
    """Check status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileTypeEnum(str, enum.Enum):
    """Output file type enumeration."""

    CSV = "csv"
    XLSX = "xlsx"


class PaymentMethodEnum(str, enum.Enum):
    """Payment method enumeration."""

    ROBOKASSA = "robokassa"
    TELEGRAM_STARS = "telegram_stars"
    MANUAL = "manual"


class PaymentStatusEnum(str, enum.Enum):
    """Payment status enumeration."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentEventTypeEnum(str, enum.Enum):
    """Payment event type enumeration for audit logging."""

    CREATED = "created"
    PRE_CHECKOUT = "pre_checkout"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY_SCHEDULED = "retry_scheduled"
    RETRY_EXECUTED = "retry_executed"


class User(Base):
    """Telegram bot user model."""

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Monetization fields
    checks_balance: Mapped[int] = mapped_column(Integer, default=0)  # No free checks on registration
    
    # Referral fields
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    referral_code: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    checks: Mapped[list["Check"]] = relationship("Check", back_populates="user")
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="user")
    referrals_made: Mapped[list["Referral"]] = relationship(
        "Referral", 
        foreign_keys="Referral.referrer_user_id",
        back_populates="referrer"
    )
    referral_received: Mapped["Referral | None"] = relationship(
        "Referral",
        foreign_keys="Referral.referred_user_id",
        back_populates="referred",
        uselist=False
    )

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, username={self.username}, balance={self.checks_balance})>"


class Check(Base):
    """Check/analysis request model."""

    __tablename__ = "checks"

    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    target_username: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[PlatformEnum] = mapped_column(
        SQLAlchemyEnum(PlatformEnum, values_callable=lambda x: [e.value for e in x]),
        default=PlatformEnum.INSTAGRAM
    )
    status: Mapped[CheckStatusEnum] = mapped_column(
        SQLAlchemyEnum(CheckStatusEnum, values_callable=lambda x: [e.value for e in x]),
        default=CheckStatusEnum.PENDING
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total_subscriptions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_followers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_non_mutual: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_type: Mapped[FileTypeEnum | None] = mapped_column(
        SQLAlchemyEnum(FileTypeEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_check_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_used: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Queue fields
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="checks")
    non_mutual_users: Mapped[list["NonMutualUser"]] = relationship(
        "NonMutualUser", back_populates="check", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Check(check_id={self.check_id}, target={self.target_username}, status={self.status})>"


class NonMutualUser(Base):
    """Non-mutual user result model."""

    __tablename__ = "non_mutual_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    check_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("checks.check_id", ondelete="CASCADE"), nullable=False
    )
    target_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_username: Mapped[str] = mapped_column(String(255), nullable=False)
    target_full_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    target_avatar_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    user_follows_target: Mapped[bool] = mapped_column(Boolean, default=True)
    target_follows_user: Mapped[bool] = mapped_column(Boolean, default=False)
    is_mutual: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    check: Mapped["Check"] = relationship("Check", back_populates="non_mutual_users")

    def __repr__(self) -> str:
        return f"<NonMutualUser(username={self.target_username}, mutual={self.is_mutual})>"


class Tariff(Base):
    """Tariff/package model for purchasing checks."""

    __tablename__ = "tariffs"

    tariff_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    checks_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price_rub: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    payments: Mapped[list["Payment"]] = relationship("Payment", back_populates="tariff")

    def __repr__(self) -> str:
        return f"<Tariff(name={self.name}, checks={self.checks_count}, price={self.price_rub})>"


class Payment(Base):
    """Payment record model."""

    __tablename__ = "payments"

    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    tariff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tariffs.tariff_id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    checks_count: Mapped[int] = mapped_column(Integer, nullable=False)  # Number of checks purchased
    payment_method: Mapped[PaymentMethodEnum] = mapped_column(
        SQLAlchemyEnum(PaymentMethodEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    status: Mapped[PaymentStatusEnum] = mapped_column(
        SQLAlchemyEnum(PaymentStatusEnum, values_callable=lambda x: [e.value for e in x]),
        default=PaymentStatusEnum.PENDING
    )
    
    # Robokassa specific fields
    robokassa_invoice_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    robokassa_payment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Telegram Stars specific fields
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="payments")
    tariff: Mapped["Tariff | None"] = relationship("Tariff", back_populates="payments")
    events: Mapped[list["PaymentEvent"]] = relationship(
        "PaymentEvent", back_populates="payment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Payment(id={self.payment_id}, user={self.user_id}, amount={self.amount}, status={self.status})>"


class PaymentEvent(Base):
    """Payment event model for audit logging."""

    __tablename__ = "payment_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.payment_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[PaymentEventTypeEnum] = mapped_column(
        SQLAlchemyEnum(PaymentEventTypeEnum, values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    status_before: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status_after: Mapped[str | None] = mapped_column(String(50), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    payment: Mapped["Payment"] = relationship("Payment", back_populates="events")

    def __repr__(self) -> str:
        return f"<PaymentEvent(event_id={self.event_id}, type={self.event_type}, payment={self.payment_id})>"


class Referral(Base):
    """Referral relationship model."""

    __tablename__ = "referrals"

    referral_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    referrer_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    referred_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    bonus_granted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    referrer: Mapped["User"] = relationship(
        "User", 
        foreign_keys=[referrer_user_id],
        back_populates="referrals_made"
    )
    referred: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referred_user_id],
        back_populates="referral_received"
    )

    def __repr__(self) -> str:
        return f"<Referral(referrer={self.referrer_user_id}, referred={self.referred_user_id})>"


class InstagramSession(Base):
    """Instagram session storage for persistent session management."""

    __tablename__ = "instagram_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        masked = self.session_id[:8] + "..." if len(self.session_id) > 8 else "***"
        return f"<InstagramSession(id={self.id}, session={masked}, active={self.is_active}, valid={self.is_valid})>"
