"""Tests for the main API router endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User


class TestHealthEndpoint:
    """Tests for the health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns OK."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


class TestUserEndpoints:
    """Tests for user-related endpoints."""

    @pytest.mark.asyncio
    async def test_ensure_user_creates_new_user(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test that ensure_user creates a new user."""
        response = await client.post(
            "/api/v1/users/ensure",
            params=sample_user_data,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == sample_user_data["user_id"]
        assert data["checks_balance"] == 0  # Regular users get 0 checks
        assert data["referral_code"] is not None

    @pytest.mark.asyncio
    async def test_ensure_user_returns_existing_user(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test that ensure_user returns existing user without changes."""
        # Create user first
        response1 = await client.post(
            "/api/v1/users/ensure",
            params=sample_user_data,
        )
        assert response1.status_code == 200
        
        # Call again - should return same user
        response2 = await client.post(
            "/api/v1/users/ensure",
            params=sample_user_data,
        )
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        assert data1["user_id"] == data2["user_id"]
        assert data1["referral_code"] == data2["referral_code"]

    @pytest.mark.asyncio
    async def test_get_user_balance(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test getting user balance."""
        # Create user first
        await client.post("/api/v1/users/ensure", params=sample_user_data)
        
        # Get balance
        response = await client.get(
            f"/api/v1/users/{sample_user_data['user_id']}/balance"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == sample_user_data["user_id"]
        assert "checks_balance" in data

    @pytest.mark.asyncio
    async def test_get_balance_user_not_found(self, client: AsyncClient):
        """Test getting balance for non-existent user."""
        response = await client.get("/api/v1/users/999999999/balance")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_user_balance(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test adding checks to user balance."""
        # Create user first
        await client.post("/api/v1/users/ensure", params=sample_user_data)
        
        # Add balance
        response = await client.post(
            f"/api/v1/users/{sample_user_data['user_id']}/balance/add",
            params={"checks_count": 10},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["checks_added"] == 10
        assert data["new_balance"] == 10


class TestCheckEndpoints:
    """Tests for check-related endpoints."""

    @pytest.mark.asyncio
    async def test_initiate_check_insufficient_balance(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test that initiating check with 0 balance fails."""
        # Create user first (0 balance)
        await client.post("/api/v1/users/ensure", params=sample_user_data)
        
        # Try to initiate check
        response = await client.post(
            "/api/v1/check/initiate",
            json={
                "username": "test_instagram",
                "platform": "instagram",
                "user_id": sample_user_data["user_id"],
            },
        )
        assert response.status_code == 402  # Payment required

    @pytest.mark.asyncio
    async def test_get_check_not_found(self, client: AsyncClient):
        """Test getting non-existent check."""
        import uuid
        fake_check_id = uuid.uuid4()
        response = await client.get(f"/api/v1/check/{fake_check_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_user_checks_empty(
        self, client: AsyncClient, sample_user_data: dict
    ):
        """Test getting check history for user with no checks."""
        # Create user first
        await client.post("/api/v1/users/ensure", params=sample_user_data)
        
        response = await client.get(
            "/api/v1/checks",
            params={"user_id": sample_user_data["user_id"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["checks"] == []
        assert data["total"] == 0


class TestQueueEndpoints:
    """Tests for queue-related endpoints."""

    @pytest.mark.asyncio
    async def test_get_queue_status(self, client: AsyncClient):
        """Test getting queue status."""
        response = await client.get("/api/v1/queue/status")
        assert response.status_code == 200
        data = response.json()
        assert "queue_length" in data
        assert "processing_count" in data

