"""Instagram session refresh service.

Handles automatic login and session ID extraction using Playwright.
Supports 2FA via TOTP if configured.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Tuple

import pyotp
from playwright.async_api import async_playwright, Browser, Page, Playwright, TimeoutError as PlaywrightTimeout
from sqlalchemy import select, update

from app.config import get_settings
from app.models.database import async_session_maker
from app.models.models import InstagramSession, RefreshCredentials
from app.services.encryption_service import decrypt_password, encrypt_password, EncryptionError
from app.services.admin_notification_service import notify_admin_session_error
from app.utils.logger import logger


class SessionRefreshError(Exception):
    """Session refresh error."""
    pass


class LoginFailedError(SessionRefreshError):
    """Login failed error."""
    pass


class TwoFactorRequiredError(SessionRefreshError):
    """2FA required but TOTP not configured."""
    pass


class SessionRefreshService:
    """Service for automatically refreshing Instagram sessions."""

    # Instagram URLs
    LOGIN_URL = "https://www.instagram.com/accounts/login/"
    HOME_URL = "https://www.instagram.com/"

    def __init__(self, headless: bool = True):
        """Initialize session refresh service.
        
        Args:
            headless: Run browser in headless mode.
        """
        self.headless = headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        
        # Load settings
        settings = get_settings()
        self.page_timeout = settings.session_page_timeout
        self.login_timeout = settings.session_login_timeout
        self.proactive_refresh_days = settings.session_refresh_days
        self.max_fail_count = settings.session_max_fail_count

    async def _get_browser(self) -> Browser:
        """Get or create browser instance."""
        if self._browser is None or not self._browser.is_connected():
            # Start playwright if not started
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-infobars',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
        return self._browser

    async def close(self):
        """Close browser and playwright instances."""
        if self._browser and self._browser.is_connected():
            await self._browser.close()
            self._browser = None
        
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def _add_stealth_scripts(self, page: Page):
        """Add anti-detection scripts to page."""
        await page.add_init_script("""
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            
            // Override plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            
            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en'],
            });
            
            // Override platform
            Object.defineProperty(navigator, 'platform', {
                get: () => 'Win32',
            });
        """)

    async def _random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0):
        """Add random delay to mimic human behavior."""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    async def login_with_playwright(
        self,
        username: str,
        password: str,
        totp_secret: str | None = None,
    ) -> str:
        """Login to Instagram using Playwright and extract session ID.
        
        Args:
            username: Instagram username.
            password: Instagram password (plain text).
            totp_secret: TOTP secret for 2FA (optional).
            
        Returns:
            Session ID cookie value.
            
        Raises:
            LoginFailedError: If login fails.
            TwoFactorRequiredError: If 2FA required but no TOTP secret.
        """
        browser = await self._get_browser()
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
        )
        
        page = await context.new_page()
        await self._add_stealth_scripts(page)
        
        # Set default timeout for all page operations
        page.set_default_timeout(self.page_timeout)
        
        try:
            logger.info(f"Starting Playwright login for {username}")
            
            # Navigate to login page
            await page.goto(self.LOGIN_URL, wait_until='networkidle', timeout=self.page_timeout)
            await self._random_delay(2, 4)
            
            # Accept cookies if dialog appears
            try:
                cookie_button = page.locator('button:has-text("Allow essential and optional cookies")')
                if await cookie_button.is_visible(timeout=3000):
                    await cookie_button.click()
                    await self._random_delay(1, 2)
            except PlaywrightTimeout:
                pass  # No cookie dialog
            
            # Fill username
            username_input = page.locator('input[name="username"]')
            await username_input.fill(username)
            await self._random_delay(0.5, 1.5)
            
            # Fill password
            password_input = page.locator('input[name="password"]')
            await password_input.fill(password)
            await self._random_delay(0.5, 1.5)
            
            # Click login button
            login_button = page.locator('button[type="submit"]')
            await login_button.click()
            
            # Wait for navigation or error
            try:
                # Check for 2FA page
                await page.wait_for_url('**/accounts/login/two_factor**', timeout=5000)
                logger.info("2FA page detected")
                
                if not totp_secret:
                    raise TwoFactorRequiredError(
                        "2FA is required but TOTP secret is not configured. "
                        "Either disable 2FA on the account or provide TOTP secret."
                    )
                
                # Generate TOTP code
                totp = pyotp.TOTP(totp_secret)
                code = totp.now()
                logger.info(f"Generated TOTP code: {code[:2]}****")
                
                # Enter 2FA code
                await self._random_delay(1, 2)
                code_input = page.locator('input[name="verificationCode"]')
                await code_input.fill(code)
                await self._random_delay(0.5, 1)
                
                # Confirm
                confirm_button = page.locator('button:has-text("Confirm")')
                await confirm_button.click()
                
            except PlaywrightTimeout:
                # No 2FA page, check for successful login or error
                pass
            
            # Wait for successful redirect to home page
            try:
                await page.wait_for_url(f'{self.HOME_URL}**', timeout=self.login_timeout)
                logger.info("Successfully logged in to Instagram")
            except PlaywrightTimeout:
                # Check for error messages
                error_message = await self._check_login_error(page)
                if error_message:
                    raise LoginFailedError(f"Login failed: {error_message}")
                raise LoginFailedError("Login timeout - could not verify successful login")
            
            # Handle "Save Login Info" dialog if it appears
            await self._random_delay(1, 2)
            try:
                not_now_button = page.locator('button:has-text("Not Now")')
                if await not_now_button.is_visible(timeout=3000):
                    await not_now_button.click()
                    await self._random_delay(1, 2)
            except PlaywrightTimeout:
                pass
            
            # Handle notifications dialog if it appears
            try:
                not_now_button = page.locator('button:has-text("Not Now")')
                if await not_now_button.is_visible(timeout=3000):
                    await not_now_button.click()
                    await self._random_delay(1, 2)
            except PlaywrightTimeout:
                pass
            
            # Extract sessionid cookie
            cookies = await context.cookies()
            session_id = None
            for cookie in cookies:
                if cookie['name'] == 'sessionid':
                    session_id = cookie['value']
                    break
            
            if not session_id:
                raise LoginFailedError("Could not extract sessionid cookie after login")
            
            logger.info(f"Successfully extracted sessionid: {session_id[:8]}...")
            return session_id
            
        except (LoginFailedError, TwoFactorRequiredError):
            raise
        except Exception as e:
            logger.error(f"Playwright login error: {e}")
            raise LoginFailedError(f"Login error: {e}")
        finally:
            await context.close()

    async def _check_login_error(self, page: Page) -> str | None:
        """Check for login error messages on page."""
        error_selectors = [
            'div[role="alert"]',
            '#slfErrorAlert',
            'p[data-testid="login-error-message"]',
        ]
        
        for selector in error_selectors:
            try:
                error_element = page.locator(selector)
                if await error_element.is_visible(timeout=1000):
                    return await error_element.text_content()
            except:
                continue
        
        return None

    async def get_active_credentials(self) -> RefreshCredentials | None:
        """Get active credentials from database.
        
        Returns:
            RefreshCredentials or None if not configured.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(RefreshCredentials)
                .where(RefreshCredentials.is_active == True)
                .order_by(RefreshCredentials.created_at.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def save_credentials(
        self,
        username: str,
        password: str,
        totp_secret: str | None = None,
    ) -> RefreshCredentials:
        """Save Instagram credentials to database (encrypted).
        
        Args:
            username: Instagram username.
            password: Instagram password (plain text, will be encrypted).
            totp_secret: TOTP secret for 2FA (optional, will be encrypted).
            
        Returns:
            Created RefreshCredentials record.
        """
        encrypted_password = encrypt_password(password)
        encrypted_totp = encrypt_password(totp_secret) if totp_secret else None
        
        async with async_session_maker() as session:
            # Deactivate existing credentials
            await session.execute(
                update(RefreshCredentials)
                .where(RefreshCredentials.is_active == True)
                .values(is_active=False)
            )
            
            # Create new credentials
            credentials = RefreshCredentials(
                username=username,
                password_encrypted=encrypted_password,
                totp_secret=encrypted_totp,
                is_active=True,
            )
            session.add(credentials)
            await session.commit()
            await session.refresh(credentials)
            
            logger.info(f"Saved new credentials for {username}")
            return credentials

    async def refresh_session(self) -> Tuple[bool, str]:
        """Refresh Instagram session using stored credentials.
        
        This is the main method for automatic session refresh.
        
        Returns:
            Tuple of (success, message).
        """
        # Get active credentials
        credentials = await self.get_active_credentials()
        if not credentials:
            return False, "No active credentials configured"
        
        try:
            # Decrypt credentials
            password = decrypt_password(credentials.password_encrypted)
            totp_secret = decrypt_password(credentials.totp_secret) if credentials.totp_secret else None
            
            # Login and get session ID
            session_id = await self.login_with_playwright(
                username=credentials.username,
                password=password,
                totp_secret=totp_secret,
            )
            
            # Save new session to database
            await self._save_session(session_id)
            
            # Update credentials last used
            await self._update_credentials_success(credentials.id)
            
            return True, f"Session refreshed successfully for {credentials.username}"
            
        except TwoFactorRequiredError as e:
            await self._update_credentials_error(credentials.id, str(e))
            await notify_admin_session_error()
            return False, str(e)
            
        except LoginFailedError as e:
            await self._update_credentials_error(credentials.id, str(e))
            await self._increment_session_fail_count(str(e))
            return False, str(e)
            
        except EncryptionError as e:
            return False, f"Encryption error: {e}"
            
        except Exception as e:
            await self._update_credentials_error(credentials.id, str(e))
            logger.exception(f"Session refresh failed: {e}")
            return False, f"Unexpected error: {e}"
        
        finally:
            await self.close()

    async def reactive_refresh(self) -> Tuple[bool, str]:
        """Reactive refresh - called when 401 error is encountered.
        
        Returns:
            Tuple of (success, message).
        """
        logger.info("Reactive session refresh triggered due to 401 error")
        
        # Mark current session as invalid
        await self._mark_active_session_invalid()
        
        # Attempt refresh
        success, message = await self.refresh_session()
        
        if success:
            logger.info("Reactive refresh successful")
        else:
            logger.error(f"Reactive refresh failed: {message}")
            await notify_admin_session_error()
        
        return success, message

    async def _save_session(self, session_id: str):
        """Save new session to database."""
        from app.services.session_service import save_session_id
        
        # Calculate next refresh time
        next_refresh = datetime.now(timezone.utc) + timedelta(days=self.proactive_refresh_days)
        
        # Save session
        ig_session = await save_session_id(session_id, notes="Auto-refreshed via Playwright")
        
        # Update next_refresh_at
        async with async_session_maker() as session:
            await session.execute(
                update(InstagramSession)
                .where(InstagramSession.id == ig_session.id)
                .values(
                    next_refresh_at=next_refresh,
                    fail_count=0,
                    last_error=None,
                )
            )
            await session.commit()
        
        logger.info(f"Session saved, next refresh at {next_refresh}")

    async def _mark_active_session_invalid(self):
        """Mark the currently active session as invalid."""
        from app.services.session_service import mark_session_invalid
        await mark_session_invalid()

    async def _update_credentials_success(self, credentials_id: int):
        """Update credentials after successful login."""
        async with async_session_maker() as session:
            await session.execute(
                update(RefreshCredentials)
                .where(RefreshCredentials.id == credentials_id)
                .values(
                    last_used_at=datetime.now(timezone.utc),
                    last_login_success=True,
                    last_error=None,
                )
            )
            await session.commit()

    async def _update_credentials_error(self, credentials_id: int, error: str):
        """Update credentials after failed login."""
        async with async_session_maker() as session:
            await session.execute(
                update(RefreshCredentials)
                .where(RefreshCredentials.id == credentials_id)
                .values(
                    last_used_at=datetime.now(timezone.utc),
                    last_login_success=False,
                    last_error=error[:500],  # Truncate if too long
                )
            )
            await session.commit()

    async def _increment_session_fail_count(self, error: str):
        """Increment fail count for active session."""
        async with async_session_maker() as session:
            result = await session.execute(
                select(InstagramSession)
                .where(InstagramSession.is_active == True)
                .limit(1)
            )
            ig_session = result.scalar_one_or_none()
            
            if ig_session:
                new_fail_count = ig_session.fail_count + 1
                await session.execute(
                    update(InstagramSession)
                    .where(InstagramSession.id == ig_session.id)
                    .values(
                        fail_count=new_fail_count,
                        last_error=error[:500],
                        refresh_attempts=InstagramSession.refresh_attempts + 1,
                    )
                )
                await session.commit()
                
                if new_fail_count >= self.max_fail_count:
                    logger.critical(
                        f"Session refresh failed {new_fail_count} times. "
                        f"Manual intervention required."
                    )

    async def should_refresh_proactively(self) -> bool:
        """Check if proactive refresh is needed.
        
        Returns:
            True if refresh is needed.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(InstagramSession)
                .where(InstagramSession.is_active == True)
                .where(InstagramSession.is_valid == True)
                .limit(1)
            )
            ig_session = result.scalar_one_or_none()
            
            if not ig_session:
                return True  # No valid session, need refresh
            
            if ig_session.next_refresh_at:
                return datetime.now(timezone.utc) >= ig_session.next_refresh_at
            
            # If no next_refresh_at, check created_at
            if ig_session.created_at:
                age = datetime.now(timezone.utc) - ig_session.created_at.replace(tzinfo=timezone.utc)
                return age.days >= self.proactive_refresh_days
            
            return False


# Singleton instance
_refresh_service: SessionRefreshService | None = None


def get_refresh_service(headless: bool = True) -> SessionRefreshService:
    """Get singleton session refresh service instance.
    
    Args:
        headless: Run browser in headless mode.
        
    Returns:
        SessionRefreshService instance.
    """
    global _refresh_service
    if _refresh_service is None:
        _refresh_service = SessionRefreshService(headless=headless)
    return _refresh_service
