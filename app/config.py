"""Application configuration settings."""

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/mutual_followers",
        alias="DATABASE_URL",
    )

    # Telegram - User bot
    telegram_token: str = Field(default="", alias="TELEGRAM_TOKEN")
    bot_username: str = Field(default="", alias="BOT_USERNAME")
    
    # Telegram - Admin notifications bot (can be same as user bot or different)
    admin_bot_token: str = Field(default="", alias="ADMIN_BOT_TOKEN")
    
    # Manager contact for user support
    manager_username: str = Field(default="issue_resolver", alias="MANAGER_USERNAME")

    # Instagram
    instagram_session_id: str = Field(default="", alias="INSTAGRAM_SESSION_ID")

    # Application
    upload_dir: str = Field(default="./data/checks", alias="UPLOAD_DIR")
    debug: bool = Field(default=True, alias="DEBUG")
    max_checks_per_day: int = Field(default=5, alias="MAX_CHECKS_PER_DAY")

    # API (for bot)
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")

    # Admin
    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")

    # Queue
    max_concurrent_checks: int = Field(default=1, alias="MAX_CONCURRENT_CHECKS")
    queue_processing_interval: int = Field(default=5, alias="QUEUE_PROCESSING_INTERVAL")

    # Referrals
    referral_bonus_checks: int = Field(default=1, alias="REFERRAL_BONUS_CHECKS")
    referral_required_count: int = Field(default=10, alias="REFERRAL_REQUIRED_COUNT")

    # Robokassa (stub for future)
    robokassa_merchant_login: str = Field(default="", alias="ROBOKASSA_MERCHANT_LOGIN")
    robokassa_password_1: str = Field(default="", alias="ROBOKASSA_PASSWORD_1")
    robokassa_password_2: str = Field(default="", alias="ROBOKASSA_PASSWORD_2")
    robokassa_test_mode: bool = Field(default=True, alias="ROBOKASSA_TEST_MODE")

    @property
    def upload_dir_path(self) -> Path:
        """Get upload directory as Path object."""
        path = Path(self.upload_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def admin_ids(self) -> list[int]:
        """Get list of admin user IDs."""
        if not self.admin_user_ids:
            return []
        return [int(uid.strip()) for uid in self.admin_user_ids.split(",") if uid.strip()]

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in self.admin_ids
    
    @property
    def effective_admin_bot_token(self) -> str:
        """Get admin bot token, fallback to main bot token if not set."""
        return self.admin_bot_token or self.telegram_token

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure upload directory exists
        Path(self.upload_dir).mkdir(parents=True, exist_ok=True)


# Mutable session ID storage (can be updated via API without restart)
_session_id_override: str | None = None


def get_instagram_session_id() -> str:
    """Get current Instagram session ID.
    
    Priority:
    1. Database (active, valid session)
    2. In-memory override (set via API)
    3. .env fallback
    
    Returns:
        Instagram session ID string, may be empty if not configured.
    """
    global _session_id_override
    
    # Try database first (using cached sync access)
    try:
        from app.services.session_service import get_active_session_id_sync
        db_session = get_active_session_id_sync()
        if db_session:
            return db_session
    except Exception:
        # Database not available yet (e.g., during startup)
        pass
    
    # Fallback to in-memory override
    if _session_id_override is not None:
        return _session_id_override
    
    # Final fallback to .env
    return get_settings().instagram_session_id


def set_instagram_session_id(session_id: str) -> None:
    """Set Instagram session ID in memory (mutable, without restart).
    
    Note: For persistent storage, use session_service.save_session_id() instead.
    This is kept for backwards compatibility with the API endpoint.
    """
    global _session_id_override
    _session_id_override = session_id


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
