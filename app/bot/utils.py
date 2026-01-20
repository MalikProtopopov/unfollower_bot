"""Shared utilities for the Telegram bot."""

from app.config import get_settings

settings = get_settings()


def get_api_url(path: str) -> str:
    """Get full API URL for a given path.
    
    Args:
        path: API path starting with / (e.g., "/users/balance")
        
    Returns:
        Full API URL (e.g., "http://backend:8000/api/v1/users/balance")
    """
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1{path}"


def get_bot_username() -> str:
    """Get the bot username from settings.
    
    Returns:
        Bot username or fallback value
    """
    return settings.bot_username or "CheckFollowersBot"


def get_manager_username() -> str:
    """Get the support manager username.
    
    Returns:
        Manager username for support contacts
    """
    return "issue_resolver"


def format_number(number: int) -> str:
    """Format a number with thousand separators.
    
    Args:
        number: Integer to format
        
    Returns:
        Formatted string (e.g., "1,234,567")
    """
    return f"{number:,}"


def truncate_text(text: str, max_length: int = 255, suffix: str = "...") -> str:
    """Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def create_progress_bar(progress: int, length: int = 10) -> str:
    """Create a text progress bar.
    
    Args:
        progress: Progress percentage (0-100)
        length: Number of characters in the bar
        
    Returns:
        Progress bar string (e.g., "█████░░░░░")
    """
    filled = int(progress / 100 * length)
    empty = length - filled
    return "█" * filled + "░" * empty


def create_referral_progress_bar(progress: int, total: int = 10) -> str:
    """Create a referral progress bar with emojis.
    
    Args:
        progress: Number of completed referrals
        total: Total referrals needed
        
    Returns:
        Progress bar with emojis (e.g., "🟢🟢🟢⚪⚪⚪⚪⚪⚪⚪")
    """
    return "🟢" * progress + "⚪" * (total - progress)

