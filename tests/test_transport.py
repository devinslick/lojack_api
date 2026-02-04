"""Tests for the transport layer."""

import asyncio
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from lojack_api.exceptions import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    ConnectionError,
    TimeoutError,
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
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )

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
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )

        # Pass the mock session to the constructor so it's treated as external
        transport = AiohttpTransport("http://example.com", session=mock_session)

        result = await transport.request("GET", "/test")
        assert result == "Hello, World!"

        await transport.close()


class TestTransportErrorHandling:
    """Tests for transport error handling."""

    @pytest.mark.asyncio
    async def test_request_timeout_error(self):
        """Test handling of timeout errors."""
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(side_effect=asyncio.TimeoutError()),
                __aexit__=AsyncMock(),
            )
        )

        transport = AiohttpTransport("http://example.com", session=mock_session)

        with pytest.raises(TimeoutError, match="timed out"):
            await transport.request("GET", "/test")

        await transport.close()

    @pytest.mark.asyncio
    async def test_request_connection_error(self):
        """Test handling of connection errors."""
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(
                    side_effect=aiohttp.ClientConnectorError(
                        MagicMock(), OSError("Connection refused")
                    )
                ),
                __aexit__=AsyncMock(),
            )
        )

        transport = AiohttpTransport("http://example.com", session=mock_session)

        with pytest.raises(ConnectionError, match="Failed to connect"):
            await transport.request("GET", "/test")

        await transport.close()

    @pytest.mark.asyncio
    async def test_request_client_error(self):
        """Test handling of general client errors."""
        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(side_effect=aiohttp.ClientError("Unknown error")),
                __aexit__=AsyncMock(),
            )
        )

        transport = AiohttpTransport("http://example.com", session=mock_session)

        with pytest.raises(ConnectionError, match="Request failed"):
            await transport.request("GET", "/test")

        await transport.close()

    @pytest.mark.asyncio
    async def test_request_http_error(self):
        """Test handling of HTTP error status codes via _handle_response."""
        transport = AiohttpTransport("http://example.com")

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.headers = {}
        mock_response.text = AsyncMock(return_value='{"error": "Server error"}')

        with pytest.raises(ApiError) as exc_info:
            await transport._handle_response(mock_response)

        assert exc_info.value.status_code == 500
        await transport.close()

    @pytest.mark.asyncio
    async def test_request_json_parsing_error_fallback_to_text(self):
        """Test that JSON parsing errors fall back to text."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(side_effect=ValueError("Invalid JSON"))
        mock_response.text = AsyncMock(return_value="Not valid JSON")

        mock_session = MagicMock(spec=aiohttp.ClientSession)
        mock_session.closed = False
        mock_session.request = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response), __aexit__=AsyncMock()
            )
        )

        transport = AiohttpTransport("http://example.com", session=mock_session)

        result = await transport.request("GET", "/test")
        assert result == "Not valid JSON"

        await transport.close()

    @pytest.mark.asyncio
    async def test_safe_read_body_error_handling(self):
        """Test that _safe_read_body handles exceptions."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.headers = {}
        mock_response.text = AsyncMock(side_effect=Exception("Read error"))

        transport = AiohttpTransport("http://example.com")
        result = await transport._safe_read_body(mock_response)
        assert result == ""

        await transport.close()

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Test that close can be called multiple times safely."""
        transport = AiohttpTransport("http://example.com")
        await transport.close()
        assert transport.closed

        # Second close should not raise
        await transport.close()
        assert transport.closed

    def test_map_http_error_with_body(self):
        """Test map_http_error includes response body."""
        transport = AiohttpTransport("http://example.com")
        error = transport._map_http_error(404, "Not Found", '{"error": "Resource not found"}')
        assert isinstance(error, ApiError)
        assert error.response_body == '{"error": "Resource not found"}'

    def test_map_http_error_empty_message(self):
        """Test map_http_error with empty message uses default."""
        transport = AiohttpTransport("http://example.com")

        error = transport._map_http_error(401, "")
        assert isinstance(error, AuthenticationError)
        assert "Authentication failed" in str(error)

        error = transport._map_http_error(403, "")
        assert isinstance(error, AuthorizationError)
        assert "Access denied" in str(error)

        error = transport._map_http_error(500, "")
        assert isinstance(error, ApiError)
        assert "HTTP 500" in str(error)


class TestTransportSSL:
    """Tests for SSL handling in transport."""

    @pytest.mark.asyncio
    async def test_transport_with_ssl_context(self):
        """Test transport creation with SSL context."""
        ssl_context = ssl.create_default_context()
        transport = AiohttpTransport(
            "https://example.com",
            ssl_context=ssl_context,
        )
        assert transport._ssl_context is ssl_context
        await transport.close()

    @pytest.mark.asyncio
    async def test_session_created_with_ssl_context(self):
        """Test that session is created with SSL context."""
        ssl_context = ssl.create_default_context()
        transport = AiohttpTransport(
            "https://example.com",
            ssl_context=ssl_context,
        )

        with patch("lojack_api.transport.aiohttp.ClientSession") as mock_client:
            with patch("lojack_api.transport.aiohttp.TCPConnector") as mock_connector:
                mock_session = MagicMock()
                mock_session.closed = False
                mock_session.close = AsyncMock()
                mock_client.return_value = mock_session

                await transport._get_session()

                # Verify TCPConnector was created with SSL context
                mock_connector.assert_called_once_with(ssl=ssl_context)

        await transport.close()

    @pytest.mark.asyncio
    async def test_session_created_without_ssl_context(self):
        """Test that session is created without SSL context."""
        transport = AiohttpTransport("https://example.com")

        with patch("lojack_api.transport.aiohttp.ClientSession") as mock_client:
            with patch("lojack_api.transport.aiohttp.TCPConnector") as mock_connector:
                mock_session = MagicMock()
                mock_session.closed = False
                mock_session.close = AsyncMock()
                mock_client.return_value = mock_session

                await transport._get_session()

                # Verify TCPConnector was created without SSL parameter
                mock_connector.assert_called_once_with()

        await transport.close()


class TestTransportSessionManagement:
    """Tests for session management."""

    @pytest.mark.asyncio
    async def test_session_reused(self):
        """Test that session is reused across requests."""
        transport = AiohttpTransport("http://example.com")

        with patch("lojack_api.transport.aiohttp.ClientSession") as mock_client:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_client.return_value = mock_session

            session1 = await transport._get_session()
            session2 = await transport._get_session()

            assert session1 is session2
            assert mock_client.call_count == 1

        await transport.close()

    @pytest.mark.asyncio
    async def test_session_recreated_if_closed(self):
        """Test that session is recreated if previous one was closed."""
        transport = AiohttpTransport("http://example.com")

        with patch("lojack_api.transport.aiohttp.ClientSession") as mock_client:
            mock_session1 = MagicMock()
            mock_session1.closed = False
            mock_session1.close = AsyncMock()

            mock_session2 = MagicMock()
            mock_session2.closed = False
            mock_session2.close = AsyncMock()

            mock_client.side_effect = [mock_session1, mock_session2]

            # First call
            session1 = await transport._get_session()
            assert session1 is mock_session1

            # Simulate session being closed
            mock_session1.closed = True

            # Second call should create new session
            session2 = await transport._get_session()
            assert session2 is mock_session2
            assert mock_client.call_count == 2

        await transport.close()

    @pytest.mark.asyncio
    async def test_close_external_session_not_closed(self):
        """Test that external sessions are not closed."""
        external_session = MagicMock(spec=aiohttp.ClientSession)
        external_session.closed = False
        external_session.close = AsyncMock()

        transport = AiohttpTransport("http://example.com", session=external_session)

        await transport.close()

        # External session close should NOT be called
        external_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_internal_session_closed(self):
        """Test that internal sessions are closed."""
        transport = AiohttpTransport("http://example.com")

        with patch("lojack_api.transport.aiohttp.ClientSession") as mock_client:
            mock_session = MagicMock()
            mock_session.closed = False
            mock_session.close = AsyncMock()
            mock_client.return_value = mock_session

            # Create session
            await transport._get_session()

            # Close transport
            await transport.close()

            # Internal session close should be called
            mock_session.close.assert_called_once()
