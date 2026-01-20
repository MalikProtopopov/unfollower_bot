"""Tests for bot utilities."""

import pytest

from app.bot.utils import (
    create_progress_bar,
    create_referral_progress_bar,
    format_number,
    get_api_url,
    truncate_text,
)


class TestGetApiUrl:
    """Tests for get_api_url function."""

    def test_basic_path(self):
        """Test basic API path generation."""
        url = get_api_url("/users/balance")
        assert "/api/v1/users/balance" in url

    def test_path_with_params(self):
        """Test path with parameters."""
        url = get_api_url("/check/123")
        assert "/api/v1/check/123" in url


class TestFormatNumber:
    """Tests for format_number function."""

    def test_small_number(self):
        """Test formatting small numbers."""
        assert format_number(123) == "123"

    def test_thousand(self):
        """Test formatting thousands."""
        assert format_number(1234) == "1,234"

    def test_million(self):
        """Test formatting millions."""
        assert format_number(1234567) == "1,234,567"

    def test_zero(self):
        """Test formatting zero."""
        assert format_number(0) == "0"


class TestTruncateText:
    """Tests for truncate_text function."""

    def test_short_text(self):
        """Test that short text is not truncated."""
        text = "Hello"
        assert truncate_text(text, max_length=10) == "Hello"

    def test_exact_length(self):
        """Test text at exact max length."""
        text = "Hello"
        assert truncate_text(text, max_length=5) == "Hello"

    def test_truncation(self):
        """Test truncation of long text."""
        text = "Hello, World!"
        result = truncate_text(text, max_length=10)
        assert len(result) == 10
        assert result.endswith("...")

    def test_custom_suffix(self):
        """Test truncation with custom suffix."""
        text = "Hello, World!"
        result = truncate_text(text, max_length=10, suffix="…")
        assert result.endswith("…")


class TestCreateProgressBar:
    """Tests for create_progress_bar function."""

    def test_zero_progress(self):
        """Test progress bar at 0%."""
        bar = create_progress_bar(0)
        assert bar == "░░░░░░░░░░"

    def test_full_progress(self):
        """Test progress bar at 100%."""
        bar = create_progress_bar(100)
        assert bar == "██████████"

    def test_half_progress(self):
        """Test progress bar at 50%."""
        bar = create_progress_bar(50)
        assert bar == "█████░░░░░"

    def test_custom_length(self):
        """Test progress bar with custom length."""
        bar = create_progress_bar(50, length=20)
        assert len(bar) == 20
        assert bar.count("█") == 10


class TestCreateReferralProgressBar:
    """Tests for create_referral_progress_bar function."""

    def test_zero_referrals(self):
        """Test referral bar with 0 referrals."""
        bar = create_referral_progress_bar(0)
        assert bar == "⚪⚪⚪⚪⚪⚪⚪⚪⚪⚪"

    def test_full_referrals(self):
        """Test referral bar with 10 referrals."""
        bar = create_referral_progress_bar(10)
        assert bar == "🟢🟢🟢🟢🟢🟢🟢🟢🟢🟢"

    def test_partial_referrals(self):
        """Test referral bar with 5 referrals."""
        bar = create_referral_progress_bar(5)
        assert bar == "🟢🟢🟢🟢🟢⚪⚪⚪⚪⚪"

