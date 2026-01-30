"""Tests for the transport layer."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from lojack_api.exceptions import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
)
from lojack_api.transport import AiohttpTransport


class TestAiohttpTransport:
    """Tests for AiohttpTransport."""

    @pytest.mark.asyncio
    async def test_session_create_close(self):
        """Test that sessions are created and closed properly."""
        transport = AiohttpTransport("http://example.com", timeout=1)

        # Create session
        session = await transport._get_session()
        assert session is not None
        assert not transport.closed

        # Close transport
        await transport.close()
        assert transport.closed
        assert transport._session is None

    @pytest.mark.asyncio
    async def test_external_session_not_closed(self):
        """Test that externally provided sessions are not closed."""
        external_session = MagicMock(spec=aiohttp.ClientSession)
        external_session.closed = False

        transport = AiohttpTransport("http://example.com", session=external_session)

        # Close should not close the external session
        await transport.close()
        external_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_base_url_trailing_slash_removed(self):
        """Test that trailing slashes are removed from base URL."""
        transport = AiohttpTransport("http://example.com/")
        assert transport.base_url == "http://example.com"
        await transport.close()

    @pytest.mark.asyncio
    async def test_closed_transport_raises_error(self):
        """Test that using a closed transport raises ConnectionError."""
        transport = AiohttpTransport("http://example.com")
        await transport.close()

        with pytest.raises(ConnectionError, match="closed"):
            await transport._get_session()

    def test_map_http_error_401(self):
        """Test that 401 status maps to AuthenticationError."""
        transport = AiohttpTransport("http://example.com")
        error = transport._map_http_error(401, "Unauthorized")
        assert isinstance(error, AuthenticationError)

    def test_map_http_error_403(self):
        """Test that 403 status maps to AuthorizationError."""
        transport = AiohttpTransport("http://example.com")
        error = transport._map_http_error(403, "Forbidden")
        assert isinstance(error, AuthorizationError)

    def test_map_http_error_other(self):
        """Test that other status codes map to ApiError."""
        transport = AiohttpTransport("http://example.com")
        error = transport._map_http_error(500, "Server Error")
        assert isinstance(error, ApiError)
        assert error.status_code == 500


class TestTransportRequest:
    """Tests for transport request handling."""

    @pytest.mark.asyncio
    async def test_request_json_response(self):
        """Test handling of JSON responses."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(return_value={"key": "value"})

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        # Pass the mock session to the constructor so it's treated as external
        transport = AiohttpTransport("http://example.com", session=mock_session)

        result = await transport.request("GET", "/test")
        assert result == {"key": "value"}

        await transport.close()

    @pytest.mark.asyncio
    async def test_request_text_response(self):
        """Test handling of text responses."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "text/plain"}
        mock_response.text = AsyncMock(return_value="Hello, World!")

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        # Pass the mock session to the constructor so it's treated as external
        transport = AiohttpTransport("http://example.com", session=mock_session)

        result = await transport.request("GET", "/test")
        assert result == "Hello, World!"

        await transport.close()
