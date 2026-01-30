"""HTTP transport layer using aiohttp.

This module handles all HTTP communication with the LoJack API.
It is designed to be compatible with Home Assistant's async patterns.
"""

from __future__ import annotations

import asyncio
import ssl
from typing import Any

import aiohttp

from .exceptions import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    TimeoutError,
)


class AiohttpTransport:
    """Async HTTP transport using aiohttp.

    This class manages HTTP communication and can accept an external
    aiohttp.ClientSession (recommended for Home Assistant) or create its own.

    Args:
        base_url: The base URL for API requests (e.g., "https://api.lojack.com").
        session: Optional existing aiohttp.ClientSession to use.
        timeout: Request timeout in seconds (default: 30).
        ssl_context: Optional SSL context for custom certificate handling.
    """

    def __init__(
        self,
        base_url: str,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._external_session = session is not None
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._ssl_context = ssl_context
        self._closed = False

    @property
    def closed(self) -> bool:
        """Return True if the transport has been closed."""
        return self._closed

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create the aiohttp session."""
        if self._closed:
            raise ConnectionError("Transport has been closed")

        if self._session is None or self._session.closed:
            ssl_arg = self._ssl_context if self._ssl_context is not None else False
            connector = aiohttp.TCPConnector(ssl=ssl_arg)
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
            )
        return self._session

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
        data: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.).
            path: API path (will be joined with base_url).
            params: Optional query parameters.
            json: Optional JSON body (will be serialized).
            data: Optional form data body.
            headers: Optional additional headers.

        Returns:
            Parsed JSON response if Content-Type is application/json,
            otherwise the response text.

        Raises:
            AuthenticationError: For 401 responses.
            AuthorizationError: For 403 responses.
            ApiError: For other HTTP errors.
            ConnectionError: For network connectivity issues.
            TimeoutError: For request timeouts.
        """
        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            async with session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=headers,
                ssl=self._ssl_context,
            ) as resp:
                return await self._handle_response(resp)

        except aiohttp.ClientResponseError as e:
            raise self._map_http_error(e.status, str(e)) from e
        except asyncio.TimeoutError as e:
            raise TimeoutError(f"Request to {url} timed out") from e
        except aiohttp.ClientConnectorError as e:
            raise ConnectionError(f"Failed to connect to {url}: {e}") from e
        except aiohttp.ClientError as e:
            raise ConnectionError(f"Request failed: {e}") from e

    async def _handle_response(self, resp: aiohttp.ClientResponse) -> Any:
        """Process the HTTP response."""
        # Check for error status codes
        if resp.status >= 400:
            body = await self._safe_read_body(resp)
            raise self._map_http_error(resp.status, body, body)

        # Parse response based on content type
        content_type = resp.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                return await resp.json()
            except (aiohttp.ContentTypeError, ValueError):
                # If JSON parsing fails, return text
                text = await resp.text()
                return text

        return await resp.text()

    async def _safe_read_body(self, resp: aiohttp.ClientResponse) -> str:
        """Safely read response body for error messages."""
        try:
            return await resp.text()
        except Exception:
            return ""

    def _map_http_error(
        self,
        status: int,
        message: str,
        body: str | None = None,
    ) -> AuthenticationError | AuthorizationError | ApiError:
        """Map HTTP status codes to appropriate exceptions."""
        if status == 401:
            return AuthenticationError(message or "Authentication failed")
        if status == 403:
            return AuthorizationError(message or "Access denied")
        return ApiError(message or f"HTTP {status}", status_code=status, response_body=body)

    async def close(self) -> None:
        """Close the transport and release resources.

        If the session was provided externally, it will NOT be closed
        (the caller is responsible for managing it).
        """
        if self._closed:
            return

        self._closed = True

        if self._session and not self._external_session:
            if not self._session.closed:
                await self._session.close()

        self._session = None


# Keep backward compatibility alias
AiohttpClient = AiohttpTransport
