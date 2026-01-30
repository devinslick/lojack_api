"""Exceptions for the LoJack client library."""

from typing import Any


class LoJackError(Exception):
    """Base exception for all LoJack client errors."""

    def __init__(self, message: str = "", *args: Any) -> None:
        self.message = message
        super().__init__(message, *args)


class AuthenticationError(LoJackError):
    """Raised when authentication fails (invalid credentials, expired token, etc.)."""

    pass


class AuthorizationError(LoJackError):
    """Raised when the user is not authorized to perform an action."""

    pass


class ApiError(LoJackError):
    """Raised when the API returns an error response."""

    def __init__(
        self,
        message: str = "",
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        if self.status_code:
            return f"{self.message} (HTTP {self.status_code})"
        return self.message


class ConnectionError(LoJackError):
    """Raised when a connection to the API cannot be established."""

    pass


class TimeoutError(LoJackError):
    """Raised when an API request times out."""

    pass


class DeviceNotFoundError(LoJackError):
    """Raised when a requested device is not found."""

    def __init__(self, device_id: str, message: str | None = None) -> None:
        self.device_id = device_id
        super().__init__(message or f"Device not found: {device_id}")


class CommandError(LoJackError):
    """Raised when a device command fails."""

    def __init__(
        self,
        command: str,
        device_id: str,
        message: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.command = command
        self.device_id = device_id
        self.reason = reason
        super().__init__(
            message or f"Command '{command}' failed for device {device_id}"
        )


class InvalidParameterError(LoJackError):
    """Raised when an invalid parameter is provided."""

    def __init__(self, parameter: str, value: Any, reason: str | None = None) -> None:
        self.parameter = parameter
        self.value = value
        self.reason = reason
        msg = f"Invalid parameter '{parameter}': {value}"
        if reason:
            msg += f" ({reason})"
        super().__init__(msg)
