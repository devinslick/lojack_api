"""LoJack Clients - An async Python library for the Spireon LoJack API.

This library provides a clean, async interface for interacting with
LoJack devices. It is designed to be compatible with Home Assistant
integrations and avoids the httpx dependency conflict.

Example usage:
    from lojack_api import LoJackClient

    async with await LoJackClient.create(username, password) as client:
        devices = await client.list_devices()
        for device in devices:
            location = await device.get_location()
            print(f"{device.name}: {location.latitude}, {location.longitude}")
"""

from .api import IDENTITY_URL, SERVICES_URL, LoJackClient
from .auth import (
    DEFAULT_APP_TOKEN,
    AuthArtifacts,
    AuthManager,
    encode_basic_auth,
    get_spireon_headers,
)
from .device import Device, Vehicle
from .exceptions import (
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
from .models import DeviceInfo, Location, VehicleInfo
from .transport import AiohttpTransport

__version__ = "0.6.0"

__all__ = [
    # Main client
    "LoJackClient",
    # API URLs
    "IDENTITY_URL",
    "SERVICES_URL",
    # Device wrappers
    "Device",
    "Vehicle",
    # Data models
    "DeviceInfo",
    "VehicleInfo",
    "Location",
    # Auth
    "AuthArtifacts",
    "AuthManager",
    "DEFAULT_APP_TOKEN",
    "encode_basic_auth",
    "get_spireon_headers",
    # Transport
    "AiohttpTransport",
    # Exceptions
    "LoJackError",
    "AuthenticationError",
    "AuthorizationError",
    "ApiError",
    "ConnectionError",
    "TimeoutError",
    "DeviceNotFoundError",
    "CommandError",
    "InvalidParameterError",
]
