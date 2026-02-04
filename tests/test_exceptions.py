"""Tests for exception classes."""

import pytest

from lojack_api.exceptions import (
    ApiError,
    AuthenticationError,
    AuthorizationError,
    CommandError,
    ConnectionError,
    DeviceNotFoundError,
    InvalidParameterError,
    LoJackError,
    TimeoutError,
)


class TestLoJackError:
    """Tests for base LoJackError."""

    def test_basic_message(self):
        """Test basic error with message."""
        error = LoJackError("Test error")
        assert error.message == "Test error"
        assert str(error) == "Test error"

    def test_empty_message(self):
        """Test error with empty message."""
        error = LoJackError()
        assert error.message == ""


class TestAuthenticationError:
    """Tests for AuthenticationError."""

    def test_inherits_from_lojack_error(self):
        """Test that AuthenticationError inherits from LoJackError."""
        error = AuthenticationError("Auth failed")
        assert isinstance(error, LoJackError)
        assert error.message == "Auth failed"


class TestAuthorizationError:
    """Tests for AuthorizationError."""

    def test_inherits_from_lojack_error(self):
        """Test that AuthorizationError inherits from LoJackError."""
        error = AuthorizationError("Access denied")
        assert isinstance(error, LoJackError)


class TestApiError:
    """Tests for ApiError."""

    def test_basic_error(self):
        """Test basic API error."""
        error = ApiError("Not found", status_code=404)
        assert error.message == "Not found"
        assert error.status_code == 404
        assert error.response_body is None

    def test_with_response_body(self):
        """Test API error with response body."""
        error = ApiError("Error", status_code=500, response_body='{"error": "Server error"}')
        assert error.response_body == '{"error": "Server error"}'

    def test_str_with_status_code(self):
        """Test string representation with status code."""
        error = ApiError("Not found", status_code=404)
        assert str(error) == "Not found (HTTP 404)"

    def test_str_without_status_code(self):
        """Test string representation without status code."""
        error = ApiError("Something went wrong")
        assert str(error) == "Something went wrong"

    def test_str_empty_message_with_status(self):
        """Test string representation with empty message but status code."""
        error = ApiError("", status_code=500)
        assert str(error) == " (HTTP 500)"


class TestConnectionError:
    """Tests for ConnectionError."""

    def test_inherits_from_lojack_error(self):
        """Test that ConnectionError inherits from LoJackError."""
        error = ConnectionError("Connection refused")
        assert isinstance(error, LoJackError)


class TestTimeoutError:
    """Tests for TimeoutError."""

    def test_inherits_from_lojack_error(self):
        """Test that TimeoutError inherits from LoJackError."""
        error = TimeoutError("Request timed out")
        assert isinstance(error, LoJackError)


class TestDeviceNotFoundError:
    """Tests for DeviceNotFoundError."""

    def test_basic_error(self):
        """Test basic device not found error."""
        error = DeviceNotFoundError("device-123")
        assert error.device_id == "device-123"
        assert "device-123" in str(error)

    def test_custom_message(self):
        """Test device not found with custom message."""
        error = DeviceNotFoundError("device-123", "Custom message")
        assert error.device_id == "device-123"
        assert error.message == "Custom message"


class TestCommandError:
    """Tests for CommandError."""

    def test_basic_error(self):
        """Test basic command error."""
        error = CommandError("locate", "device-123")
        assert error.command == "locate"
        assert error.device_id == "device-123"
        assert error.reason is None
        assert "locate" in str(error)
        assert "device-123" in str(error)

    def test_with_custom_message(self):
        """Test command error with custom message."""
        error = CommandError("locate", "device-123", message="Custom failure")
        assert error.message == "Custom failure"

    def test_with_reason(self):
        """Test command error with reason."""
        error = CommandError("locate", "device-123", reason="Device offline")
        assert error.reason == "Device offline"


class TestInvalidParameterError:
    """Tests for InvalidParameterError."""

    def test_basic_error(self):
        """Test basic invalid parameter error."""
        error = InvalidParameterError("radius", -100)
        assert error.parameter == "radius"
        assert error.value == -100
        assert error.reason is None
        assert "radius" in str(error)
        assert "-100" in str(error)

    def test_with_reason(self):
        """Test invalid parameter error with reason."""
        error = InvalidParameterError("radius", -100, reason="must be positive")
        assert error.reason == "must be positive"
        assert "must be positive" in str(error)
