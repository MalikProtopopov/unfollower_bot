"""Centralized HTTP client for API communication."""

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx

from app.bot.utils import get_api_url
from app.utils.logger import logger


# Default timeout for API requests
DEFAULT_TIMEOUT = 30.0

# Shorter timeout for pre-checkout validation (Telegram requires < 10s response)
PRE_CHECKOUT_TIMEOUT = 8.0


class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(message)


class APINotFoundError(APIError):
    """Resource not found (404)."""

    pass


class APIPaymentRequiredError(APIError):
    """Payment required (402)."""

    pass


class APIBadRequestError(APIError):
    """Bad request (400)."""

    pass


class APITimeoutError(APIError):
    """Request timeout."""

    pass


class APIClient:
    """Async HTTP client for backend API communication."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        """Initialize API client.
        
        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    @asynccontextmanager
    async def _get_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """Get or create HTTP client as context manager.
        
        Yields:
            httpx.AsyncClient instance
        """
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            yield client

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make GET request to API.
        
        Args:
            path: API path (e.g., "/users/123/balance")
            params: Optional query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            APIError: On request failure
        """
        url = get_api_url(path)
        try:
            async with self._get_client() as client:
                response = await client.get(url, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException as e:
            logger.error(f"Timeout on GET {url}: {e}")
            raise APITimeoutError(f"Request timeout: {path}")

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make POST request to API.
        
        Args:
            path: API path (e.g., "/check/initiate")
            json: Optional JSON body
            params: Optional query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            APIError: On request failure
        """
        url = get_api_url(path)
        try:
            async with self._get_client() as client:
                response = await client.post(url, json=json, params=params)
                return self._handle_response(response)
        except httpx.TimeoutException as e:
            logger.error(f"Timeout on POST {url}: {e}")
            raise APITimeoutError(f"Request timeout: {path}")

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and raise appropriate exceptions.
        
        Args:
            response: HTTP response
            
        Returns:
            JSON response as dictionary
            
        Raises:
            APIError: On error status codes
        """
        if response.status_code == 200:
            return response.json()
        
        # Try to extract error detail from response
        try:
            error_data = response.json()
            detail = error_data.get("detail", str(error_data))
        except Exception:
            detail = response.text or "Unknown error"

        if response.status_code == 404:
            raise APINotFoundError(
                f"Resource not found",
                status_code=404,
                detail=detail,
            )
        elif response.status_code == 402:
            raise APIPaymentRequiredError(
                "Payment required",
                status_code=402,
                detail=detail,
            )
        elif response.status_code == 400:
            raise APIBadRequestError(
                f"Bad request",
                status_code=400,
                detail=detail,
            )
        else:
            raise APIError(
                f"API error: {response.status_code}",
                status_code=response.status_code,
                detail=detail,
            )


# Singleton instance for common use
api_client = APIClient()

# Separate instance for pre-checkout with shorter timeout
pre_checkout_client = APIClient(timeout=PRE_CHECKOUT_TIMEOUT)


# Convenience functions for simple use cases
async def api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make GET request using default client.
    
    Args:
        path: API path
        params: Optional query parameters
        
    Returns:
        JSON response
    """
    return await api_client.get(path, params)


async def api_post(
    path: str,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make POST request using default client.
    
    Args:
        path: API path
        json: Optional JSON body
        params: Optional query parameters
        
    Returns:
        JSON response
    """
    return await api_client.post(path, json, params)

