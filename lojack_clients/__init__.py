"""LoJack Clients - An async Python library for the LoJack API.

This library provides a clean, async interface for interacting with
LoJack devices. It is designed to be compatible with Home Assistant
integrations.

Example usage:
    from lojack_clients import LoJackClient

    async with await LoJackClient.create(url, username, password) as client:
        devices = await client.list_devices()
        for device in devices:
            location = await device.get_location()
            print(f"{device.name}: {location.latitude}, {location.longitude}")
"""

from .api import LoJackClient
from .auth import AuthArtifacts, AuthManager
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

__version__ = "0.2.0"

__all__ = [
    # Main client
    "LoJackClient",
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
