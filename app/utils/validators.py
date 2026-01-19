"""Input validation utilities."""

import re
from urllib.parse import urlparse


# Instagram username pattern: 1-30 chars, letters, numbers, dots, underscores
INSTAGRAM_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._]{1,30}$")

# Instagram URL patterns
INSTAGRAM_URL_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9._]{1,30})/?"),
    re.compile(r"(?:https?://)?(?:www\.)?instagr\.am/([a-zA-Z0-9._]{1,30})/?"),
]


def validate_instagram_username(username: str) -> bool:
    """Validate Instagram username format.

    Args:
        username: Instagram username to validate

    Returns:
        True if valid, False otherwise
    """
    if not username:
        return False

    # Remove @ prefix if present
    clean_username = username.lstrip("@")

    return bool(INSTAGRAM_USERNAME_PATTERN.match(clean_username))


def normalize_instagram_username(input_string: str) -> str | None:
    """Extract and normalize Instagram username from input.

    Handles:
    - Plain username: user123
    - Username with @: @user123
    - Full URL: https://instagram.com/user123

    Args:
        input_string: User input (username or URL)

    Returns:
        Normalized username or None if invalid
    """
    if not input_string:
        return None

    input_string = input_string.strip()

    # Try to extract from URL first
    for pattern in INSTAGRAM_URL_PATTERNS:
        match = pattern.search(input_string)
        if match:
            username = match.group(1)
            if validate_instagram_username(username):
                return username.lower()

    # Try as plain username
    clean_username = input_string.lstrip("@")
    if validate_instagram_username(clean_username):
        return clean_username.lower()

    return None


def extract_instagram_username(text: str) -> str | None:
    """Extract Instagram username from any text input.

    Args:
        text: Input text that may contain username or URL

    Returns:
        Extracted username or None
    """
    return normalize_instagram_username(text)

