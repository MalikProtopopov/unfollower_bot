"""Tests for payment service."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Payment, PaymentStatusEnum, Tariff, User
from app.services.payment_service import (
    PaymentAlreadyCompletedError,
    PaymentAmountMismatchError,
    PaymentNotFoundError,
    TariffNotAvailableError,
    TariffNotFoundError,
    UserNotFoundError,
    complete_telegram_stars_payment,
    create_telegram_stars_payment,
    fail_telegram_stars_payment,
    validate_telegram_stars_payment,
)


class TestCreateTelegramStarsPayment:
    """Tests for create_telegram_stars_payment function."""

    @pytest.fixture
    async def setup_data(self, test_session: AsyncSession) -> tuple[User, Tariff]:
        """Create test user and tariff."""
        user = User(
            user_id=111111,
            username="payment_test_user",
            referral_code="ref_111111",
            checks_balance=0,
        )
        tariff = Tariff(
            name="Test Package",
            checks_count=5,
            price_rub=199,
            price_stars=200,
            is_active=True,
            sort_order=1,
        )
        test_session.add(user)
        test_session.add(tariff)
        await test_session.commit()
        await test_session.refresh(user)
        await test_session.refresh(tariff)
        return user, tariff

    @pytest.mark.asyncio
    async def test_create_payment_success(
        self, test_session: AsyncSession, setup_data: tuple[User, Tariff]
    ):
        """Test successful payment creation."""
        user, tariff = setup_data
        
        payment, returned_tariff = await create_telegram_stars_payment(
            session=test_session,
            user_id=user.user_id,
            tariff_id=tariff.tariff_id,
        )
        
        assert payment is not None
        assert payment.user_id == user.user_id
        assert payment.tariff_id == tariff.tariff_id
        assert payment.amount == tariff.price_stars
        assert payment.currency == "XTR"
        assert payment.status == PaymentStatusEnum.PENDING
        assert returned_tariff.name == tariff.name

    @pytest.mark.asyncio
    async def test_create_payment_user_not_found(
        self, test_session: AsyncSession, setup_data: tuple[User, Tariff]
    ):
        """Test payment creation with non-existent user."""
        _, tariff = setup_data
        
        with pytest.raises(UserNotFoundError):
            await create_telegram_stars_payment(
                session=test_session,
                user_id=999999,
                tariff_id=tariff.tariff_id,
            )

    @pytest.mark.asyncio
    async def test_create_payment_tariff_not_found(
        self, test_session: AsyncSession, setup_data: tuple[User, Tariff]
    ):
        """Test payment creation with non-existent tariff."""
        user, _ = setup_data
        
        with pytest.raises(TariffNotFoundError):
            await create_telegram_stars_payment(
                session=test_session,
                user_id=user.user_id,
                tariff_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_create_payment_inactive_tariff(
        self, test_session: AsyncSession, setup_data: tuple[User, Tariff]
    ):
        """Test payment creation with inactive tariff."""
        user, tariff = setup_data
        
        # Deactivate tariff
        tariff.is_active = False
        await test_session.commit()
        
        with pytest.raises(TariffNotAvailableError):
            await create_telegram_stars_payment(
                session=test_session,
                user_id=user.user_id,
                tariff_id=tariff.tariff_id,
            )


class TestCompleteTelegramStarsPayment:
    """Tests for complete_telegram_stars_payment function."""

    @pytest.fixture
    async def pending_payment(self, test_session: AsyncSession) -> tuple[Payment, User, Tariff]:
        """Create a pending payment for testing."""
        user = User(
            user_id=222222,
            username="complete_test_user",
            referral_code="ref_222222",
            checks_balance=0,
        )
        tariff = Tariff(
            name="Complete Test",
            checks_count=3,
            price_rub=99,
            price_stars=100,
            is_active=True,
            sort_order=1,
        )
        test_session.add(user)
        test_session.add(tariff)
        await test_session.flush()
        
        payment = Payment(
            user_id=user.user_id,
            tariff_id=tariff.tariff_id,
            amount=100,
            currency="XTR",
            checks_count=3,
            payment_method="telegram_stars",
            status=PaymentStatusEnum.PENDING,
        )
        test_session.add(payment)
        await test_session.commit()
        await test_session.refresh(payment)
        await test_session.refresh(user)
        
        return payment, user, tariff

    @pytest.mark.asyncio
    async def test_complete_payment_success(
        self, test_session: AsyncSession, pending_payment: tuple[Payment, User, Tariff]
    ):
        """Test successful payment completion."""
        payment, user, tariff = pending_payment
        initial_balance = user.checks_balance
        
        completed_payment, updated_user = await complete_telegram_stars_payment(
            session=test_session,
            payment_id=payment.payment_id,
            telegram_payment_charge_id="charge_123",
            total_amount=100,
        )
        
        assert completed_payment.status == PaymentStatusEnum.COMPLETED
        assert completed_payment.telegram_payment_charge_id == "charge_123"
        assert updated_user.checks_balance == initial_balance + tariff.checks_count

    @pytest.mark.asyncio
    async def test_complete_payment_not_found(self, test_session: AsyncSession):
        """Test completing non-existent payment."""
        with pytest.raises(PaymentNotFoundError):
            await complete_telegram_stars_payment(
                session=test_session,
                payment_id=uuid.uuid4(),
                telegram_payment_charge_id="charge_123",
                total_amount=100,
            )

    @pytest.mark.asyncio
    async def test_complete_payment_amount_mismatch(
        self, test_session: AsyncSession, pending_payment: tuple[Payment, User, Tariff]
    ):
        """Test completing payment with wrong amount."""
        payment, _, _ = pending_payment
        
        with pytest.raises(PaymentAmountMismatchError):
            await complete_telegram_stars_payment(
                session=test_session,
                payment_id=payment.payment_id,
                telegram_payment_charge_id="charge_123",
                total_amount=999,  # Wrong amount
            )

    @pytest.mark.asyncio
    async def test_complete_payment_idempotent(
        self, test_session: AsyncSession, pending_payment: tuple[Payment, User, Tariff]
    ):
        """Test that completing same payment twice is idempotent."""
        payment, user, tariff = pending_payment
        
        # Complete first time
        await complete_telegram_stars_payment(
            session=test_session,
            payment_id=payment.payment_id,
            telegram_payment_charge_id="charge_123",
            total_amount=100,
        )
        
        # Complete again with same charge_id - should be idempotent
        completed_payment, updated_user = await complete_telegram_stars_payment(
            session=test_session,
            payment_id=payment.payment_id,
            telegram_payment_charge_id="charge_123",
            total_amount=100,
        )
        
        # Balance should not be doubled
        assert updated_user.checks_balance == tariff.checks_count


class TestFailTelegramStarsPayment:
    """Tests for fail_telegram_stars_payment function."""

    @pytest.fixture
    async def pending_payment(self, test_session: AsyncSession) -> Payment:
        """Create a pending payment for testing."""
        user = User(
            user_id=333333,
            username="fail_test_user",
            referral_code="ref_333333",
            checks_balance=0,
        )
        tariff = Tariff(
            name="Fail Test",
            checks_count=1,
            price_rub=50,
            price_stars=50,
            is_active=True,
            sort_order=1,
        )
        test_session.add(user)
        test_session.add(tariff)
        await test_session.flush()
        
        payment = Payment(
            user_id=user.user_id,
            tariff_id=tariff.tariff_id,
            amount=50,
            currency="XTR",
            checks_count=1,
            payment_method="telegram_stars",
            status=PaymentStatusEnum.PENDING,
        )
        test_session.add(payment)
        await test_session.commit()
        await test_session.refresh(payment)
        
        return payment

    @pytest.mark.asyncio
    async def test_fail_payment_success(
        self, test_session: AsyncSession, pending_payment: Payment
    ):
        """Test marking payment as failed."""
        failed_payment = await fail_telegram_stars_payment(
            session=test_session,
            payment_id=pending_payment.payment_id,
            error_reason="user_cancelled",
            error_message="User cancelled the payment",
        )
        
        assert failed_payment.status == PaymentStatusEnum.FAILED

    @pytest.mark.asyncio
    async def test_fail_completed_payment(
        self, test_session: AsyncSession, pending_payment: Payment
    ):
        """Test that failing a completed payment raises error."""
        # Complete the payment first
        pending_payment.status = PaymentStatusEnum.COMPLETED
        await test_session.commit()
        
        with pytest.raises(PaymentAlreadyCompletedError):
            await fail_telegram_stars_payment(
                session=test_session,
                payment_id=pending_payment.payment_id,
                error_reason="test",
            )

