"""Instagram GraphQL scraper for fetching followers and following lists."""

import asyncio
import hashlib
import json
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from app.config import get_settings
from app.utils.logger import logger


@dataclass
class InstagramUser:
    """Instagram user data."""

    user_id: str
    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_private: bool = False
    is_verified: bool = False


class InstagramScraperError(Exception):
    """Base exception for Instagram scraper."""

    pass


class UserNotFoundError(InstagramScraperError):
    """User not found exception."""

    pass


class PrivateAccountError(InstagramScraperError):
    """Private account exception."""

    pass


class RateLimitError(InstagramScraperError):
    """Rate limit exceeded exception."""

    pass


class SessionExpiredError(InstagramScraperError):
    """Instagram session expired or invalid (401 Unauthorized)."""

    pass


class IncompleteDataError(InstagramScraperError):
    """Data fetch was interrupted and results are incomplete.
    
    This error is raised when rate limiting or other errors occur
    mid-fetch, resulting in partial data that should not be used
    for comparison (would produce incorrect results).
    """

    def __init__(self, message: str, fetched_count: int, connection_type: str):
        self.fetched_count = fetched_count
        self.connection_type = connection_type
        super().__init__(message)


class InstagramScraper:
    """Instagram GraphQL scraper for fetching user data."""

    BASE_URL = "https://www.instagram.com"
    GRAPHQL_URL = f"{BASE_URL}/graphql/query/"

    # GraphQL query hashes (these may change over time)
    QUERY_HASH_FOLLOWERS = "c76146de99bb02f6415203be841dd25a"
    QUERY_HASH_FOLLOWING = "d04b0a864b4b54837c0d870b0e77e076"
    QUERY_HASH_USER_INFO = "c9100bf9110dd6361671f113dd02e7d6"

    # User agents for rotation
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]

    def __init__(
        self,
        session_id: str | None = None,
        max_retries: int = 3,
        delay_range: tuple[float, float] = (1.0, 3.0),
    ):
        """Initialize scraper.

        Args:
            session_id: Instagram session ID cookie for authenticated requests
            max_retries: Maximum number of retry attempts
            delay_range: Min and max delay between requests in seconds
        """
        self.session_id = session_id
        self.max_retries = max_retries
        self.delay_range = delay_range
        self._client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get request headers with random user agent."""
        headers = {
            "User-Agent": random.choice(self.USER_AGENTS),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "X-IG-App-ID": "936619743392459",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": self.BASE_URL,
            "Origin": self.BASE_URL,
        }
        return headers

    def _get_cookies(self) -> dict[str, str]:
        """Get cookies for requests."""
        cookies = {
            "ig_did": hashlib.md5(str(time.time()).encode()).hexdigest()[:32],
            "ig_nrcb": "1",
        }
        if self.session_id:
            cookies["sessionid"] = self.session_id
        return cookies

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self._get_headers(),
                cookies=self._get_cookies(),
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _random_delay(self):
        """Add random delay between requests."""
        delay = random.uniform(*self.delay_range)
        await asyncio.sleep(delay)

    async def _make_request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            JSON response data

        Raises:
            InstagramScraperError: On request failure
        """
        client = await self._get_client()
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff
                    await asyncio.sleep(2**attempt + random.uniform(0, 1))

                # Rotate user agent on retries
                client.headers["User-Agent"] = random.choice(self.USER_AGENTS)

                response = await client.get(url, params=params)

                if response.status_code == 401:
                    logger.error(f"Session expired (401 Unauthorized) on attempt {attempt + 1}")
                    raise SessionExpiredError("Instagram session expired or invalid (401 Unauthorized)")

                if response.status_code == 429:
                    logger.warning(f"Rate limited on attempt {attempt + 1}")
                    raise RateLimitError("Instagram rate limit exceeded")

                if response.status_code == 404:
                    raise UserNotFoundError("User not found")

                response.raise_for_status()

                data = response.json()
                return data

            except SessionExpiredError:
                raise
            except RateLimitError:
                raise
            except UserNotFoundError:
                raise
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(f"HTTP error on attempt {attempt + 1}: {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"Request error on attempt {attempt + 1}: {e}")

        raise InstagramScraperError(f"Failed after {self.max_retries} attempts: {last_error}")

    async def get_user_info(self, username: str) -> InstagramUser:
        """Get user information by username.

        Args:
            username: Instagram username

        Returns:
            InstagramUser object

        Raises:
            UserNotFoundError: If user doesn't exist
            InstagramScraperError: On other errors
        """
        await self._random_delay()

        # Try web profile endpoint first
        url = f"{self.BASE_URL}/api/v1/users/web_profile_info/"
        params = {"username": username}

        try:
            data = await self._make_request(url, params)
            user_data = data.get("data", {}).get("user")

            if not user_data:
                raise UserNotFoundError(f"User @{username} not found")

            return InstagramUser(
                user_id=user_data.get("id", ""),
                username=user_data.get("username", username),
                full_name=user_data.get("full_name"),
                avatar_url=user_data.get("profile_pic_url"),
                is_private=user_data.get("is_private", False),
                is_verified=user_data.get("is_verified", False),
            )

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise UserNotFoundError(f"User @{username} not found")
            raise InstagramScraperError(f"Failed to get user info: {e}")

    async def _fetch_connections(
        self,
        user_id: str,
        query_hash: str,
        connection_type: str,
        max_users: int = 10000,
        on_progress: Callable | None = None,
    ) -> list[InstagramUser]:
        """Fetch user connections (followers or following).

        Args:
            user_id: Instagram user ID
            query_hash: GraphQL query hash
            connection_type: Either "edge_followed_by" or "edge_follow"
            max_users: Maximum users to fetch
            on_progress: Callback for progress updates

        Returns:
            List of InstagramUser objects
        """
        users = []
        has_next = True
        end_cursor = None
        batch_size = 50

        while has_next and len(users) < max_users:
            await self._random_delay()

            variables = {
                "id": user_id,
                "first": batch_size,
            }
            if end_cursor:
                variables["after"] = end_cursor

            params = {
                "query_hash": query_hash,
                "variables": json.dumps(variables),
            }

            try:
                data = await self._make_request(self.GRAPHQL_URL, params)
                user_data = data.get("data", {}).get("user", {})

                if not user_data:
                    logger.warning("No user data in GraphQL response")
                    break

                edge_data = user_data.get(connection_type, {})
                edges = edge_data.get("edges", [])

                for edge in edges:
                    node = edge.get("node", {})
                    users.append(
                        InstagramUser(
                            user_id=node.get("id", ""),
                            username=node.get("username", ""),
                            full_name=node.get("full_name"),
                            avatar_url=node.get("profile_pic_url"),
                            is_private=node.get("is_private", False),
                            is_verified=node.get("is_verified", False),
                        )
                    )

                page_info = edge_data.get("page_info", {})
                has_next = page_info.get("has_next_page", False)
                end_cursor = page_info.get("end_cursor")

                # Report progress
                if on_progress:
                    total = edge_data.get("count", len(users))
                    progress = min(100, int(len(users) / max(total, 1) * 100))
                    on_progress(progress, len(users), total)

                logger.info(f"Fetched {len(users)} {connection_type} users")

            except SessionExpiredError:
                logger.error(
                    f"Session expired while fetching {connection_type}. "
                    f"Stopping fetch operation immediately. "
                    f"Already fetched {len(users)} users before session expiry."
                )
                raise
            except RateLimitError as e:
                logger.error(
                    f"Rate limit hit while fetching {connection_type}. "
                    f"Fetched {len(users)} users before rate limit. Data is incomplete!"
                )
                raise IncompleteDataError(
                    f"Rate limit hit while fetching {connection_type}. "
                    f"Only {len(users)} users fetched. Results would be inaccurate.",
                    fetched_count=len(users),
                    connection_type=connection_type,
                ) from e
            except Exception as e:
                logger.error(
                    f"Error fetching {connection_type}: {e}. "
                    f"Fetched {len(users)} users before error. Data may be incomplete!"
                )
                raise IncompleteDataError(
                    f"Error while fetching {connection_type}: {e}. "
                    f"Only {len(users)} users fetched. Results would be inaccurate.",
                    fetched_count=len(users),
                    connection_type=connection_type,
                ) from e

        return users

    async def get_followers(
        self,
        username: str,
        max_users: int | None = None,
        on_progress: Callable | None = None,
    ) -> list[InstagramUser]:
        """Get user's followers.

        Args:
            username: Instagram username
            max_users: Maximum followers to fetch (default from settings)
            on_progress: Progress callback

        Returns:
            List of followers
        """
        if max_users is None:
            max_users = get_settings().max_account_size
            
        user_info = await self.get_user_info(username)

        if user_info.is_private and not self.session_id:
            raise PrivateAccountError(f"Account @{username} is private")

        logger.info(f"Fetching followers for @{username} (ID: {user_info.user_id})")

        return await self._fetch_connections(
            user_id=user_info.user_id,
            query_hash=self.QUERY_HASH_FOLLOWERS,
            connection_type="edge_followed_by",
            max_users=max_users,
            on_progress=on_progress,
        )

    async def get_following(
        self,
        username: str,
        max_users: int | None = None,
        on_progress: Callable | None = None,
    ) -> list[InstagramUser]:
        """Get user's following list.

        Args:
            username: Instagram username
            max_users: Maximum following to fetch (default from settings)
            on_progress: Progress callback

        Returns:
            List of following
        """
        if max_users is None:
            max_users = get_settings().max_account_size
            
        user_info = await self.get_user_info(username)

        if user_info.is_private and not self.session_id:
            raise PrivateAccountError(f"Account @{username} is private")

        logger.info(f"Fetching following for @{username} (ID: {user_info.user_id})")

        return await self._fetch_connections(
            user_id=user_info.user_id,
            query_hash=self.QUERY_HASH_FOLLOWING,
            connection_type="edge_follow",
            max_users=max_users,
            on_progress=on_progress,
        )

    async def get_non_mutual_followers(
        self,
        username: str,
        max_users: int | None = None,
        on_progress: Callable | None = None,
    ) -> tuple[list[InstagramUser], list[InstagramUser], list[InstagramUser]]:
        """Get non-mutual followers analysis.

        Args:
            username: Instagram username
            max_users: Maximum users to fetch per list (default from settings)
            on_progress: Progress callback (receives: progress%, stage)

        Returns:
            Tuple of (followers, following, non_mutual)
            non_mutual = people user follows but who don't follow back
        """
        if max_users is None:
            max_users = get_settings().max_account_size
            
        # Get user info ONCE
        if on_progress:
            on_progress(5, "Getting user info...")

        user_info = await self.get_user_info(username)

        if user_info.is_private and not self.session_id:
            raise PrivateAccountError(f"Account @{username} is private")

        user_id = user_info.user_id
        logger.info(f"Starting analysis for @{username} (ID: {user_id})")

        # Fetch followers using user_id directly
        if on_progress:
            on_progress(10, "Fetching followers...")

        logger.info(f"Fetching followers for @{username} (ID: {user_id})")
        followers = await self._fetch_connections(
            user_id=user_id,
            query_hash=self.QUERY_HASH_FOLLOWERS,
            connection_type="edge_followed_by",
            max_users=max_users,
            on_progress=lambda p, c, t: on_progress(10 + p * 0.4, f"Followers: {c}/{t}") if on_progress else None,
        )

        # Delay between fetching followers and following to avoid rate limiting
        # Increased delay to prevent Instagram account blocking
        await asyncio.sleep(6)

        # Fetch following using same user_id
        if on_progress:
            on_progress(50, "Fetching following...")

        logger.info(f"Fetching following for @{username} (ID: {user_id})")
        following = await self._fetch_connections(
            user_id=user_id,
            query_hash=self.QUERY_HASH_FOLLOWING,
            connection_type="edge_follow",
            max_users=max_users,
            on_progress=lambda p, c, t: on_progress(50 + p * 0.4, f"Following: {c}/{t}") if on_progress else None,
        )

        # Calculate non-mutual
        if on_progress:
            on_progress(90, "Calculating non-mutual...")

        follower_ids = {f.user_id for f in followers}
        non_mutual = [f for f in following if f.user_id not in follower_ids]

        if on_progress:
            on_progress(100, "Complete")

        logger.info(
            f"Analysis complete for @{username}: "
            f"{len(followers)} followers, {len(following)} following, "
            f"{len(non_mutual)} non-mutual"
        )

        return followers, following, non_mutual

