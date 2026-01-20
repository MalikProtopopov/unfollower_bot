"""Tests for payment API endpoints."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Tariff, User


class TestTelegramStarsPayments:
    """Tests for Telegram Stars payment endpoints."""

    @pytest.fixture
    async def user_with_tariff(
        self, test_session: AsyncSession, sample_user_data: dict, sample_tariff_data: dict
    ) -> tuple[User, Tariff]:
        """Create user and tariff for payment tests."""
        # Create user
        user = User(
            user_id=sample_user_data["user_id"],
            username=sample_user_data["username"],
            first_name=sample_user_data["first_name"],
            referral_code=f"ref_{sample_user_data['user_id']}",
            checks_balance=0,
        )
        test_session.add(user)
        
        # Create tariff
        tariff = Tariff(
            name=sample_tariff_data["name"],
            description=sample_tariff_data["description"],
            checks_count=sample_tariff_data["checks_count"],
            price_rub=sample_tariff_data["price_rub"],
            price_stars=sample_tariff_data["price_stars"],
            is_active=sample_tariff_data["is_active"],
            sort_order=sample_tariff_data["sort_order"],
        )
        test_session.add(tariff)
        
        await test_session.commit()
        await test_session.refresh(user)
        await test_session.refresh(tariff)
        
        return user, tariff

    @pytest.mark.asyncio
    async def test_create_stars_payment(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test creating a Telegram Stars payment."""
        user, tariff = user_with_tariff
        
        response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user.user_id
        assert data["tariff_id"] == str(tariff.tariff_id)
        assert data["tariff_name"] == tariff.name
        assert data["checks_count"] == tariff.checks_count
        assert data["price_stars"] == tariff.price_stars
        assert data["currency"] == "XTR"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_stars_payment_user_not_found(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test creating payment with non-existent user."""
        _, tariff = user_with_tariff
        
        response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": 999999999,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_stars_payment_tariff_not_found(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test creating payment with non-existent tariff."""
        user, _ = user_with_tariff
        
        response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(uuid.uuid4()),
            },
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_validate_stars_payment(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test validating a Telegram Stars payment."""
        user, tariff = user_with_tariff
        
        # Create payment first
        create_response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        payment_id = create_response.json()["payment_id"]
        
        # Validate payment
        response = await client.post(
            f"/api/v1/payments/telegram-stars/validate/{payment_id}",
            params={"expected_amount": tariff.price_stars},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_stars_payment_amount_mismatch(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test validating payment with wrong amount."""
        user, tariff = user_with_tariff
        
        # Create payment first
        create_response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        payment_id = create_response.json()["payment_id"]
        
        # Validate with wrong amount
        response = await client.post(
            f"/api/v1/payments/telegram-stars/validate/{payment_id}",
            params={"expected_amount": 9999},  # Wrong amount
        )
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_complete_stars_payment(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test completing a Telegram Stars payment."""
        user, tariff = user_with_tariff
        
        # Create payment first
        create_response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        payment_id = create_response.json()["payment_id"]
        
        # Complete payment
        response = await client.post(
            "/api/v1/payments/telegram-stars/complete",
            json={
                "payment_id": payment_id,
                "telegram_payment_charge_id": "test_charge_123",
                "total_amount": tariff.price_stars,
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["checks_added"] == tariff.checks_count
        assert data["user_checks_balance"] == tariff.checks_count

    @pytest.mark.asyncio
    async def test_complete_stars_payment_idempotent(
        self, client: AsyncClient, user_with_tariff: tuple[User, Tariff]
    ):
        """Test that completing payment twice is idempotent."""
        user, tariff = user_with_tariff
        
        # Create payment
        create_response = await client.post(
            "/api/v1/payments/telegram-stars/create",
            json={
                "user_id": user.user_id,
                "tariff_id": str(tariff.tariff_id),
            },
        )
        payment_id = create_response.json()["payment_id"]
        
        # Complete payment twice
        complete_request = {
            "payment_id": payment_id,
            "telegram_payment_charge_id": "test_charge_123",
            "total_amount": tariff.price_stars,
        }
        
        response1 = await client.post(
            "/api/v1/payments/telegram-stars/complete",
            json=complete_request,
        )
        assert response1.status_code == 200
        
        response2 = await client.post(
            "/api/v1/payments/telegram-stars/complete",
            json=complete_request,
        )
        # Second call should return 409 (Conflict) or 200 for idempotency
        assert response2.status_code in [200, 409]


class TestTariffEndpoints:
    """Tests for tariff endpoints."""

    @pytest.fixture
    async def active_tariffs(self, test_session: AsyncSession) -> list[Tariff]:
        """Create active tariffs for testing."""
        tariffs = [
            Tariff(
                name="Basic",
                description="1 check",
                checks_count=1,
                price_rub=99,
                price_stars=100,
                is_active=True,
                sort_order=1,
            ),
            Tariff(
                name="Pro",
                description="5 checks",
                checks_count=5,
                price_rub=399,
                price_stars=400,
                is_active=True,
                sort_order=2,
            ),
            Tariff(
                name="Inactive",
                description="Should not appear",
                checks_count=10,
                price_rub=999,
                price_stars=1000,
                is_active=False,
                sort_order=3,
            ),
        ]
        
        for tariff in tariffs:
            test_session.add(tariff)
        
        await test_session.commit()
        
        return tariffs

    @pytest.mark.asyncio
    async def test_get_tariffs(self, client: AsyncClient, active_tariffs: list[Tariff]):
        """Test getting active tariffs."""
        response = await client.get("/api/v1/tariffs")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should only return active tariffs
        assert len(data["tariffs"]) == 2
        tariff_names = [t["name"] for t in data["tariffs"]]
        assert "Basic" in tariff_names
        assert "Pro" in tariff_names
        assert "Inactive" not in tariff_names

