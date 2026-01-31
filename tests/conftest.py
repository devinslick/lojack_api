"""Shared fixtures for tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lojack_api.auth import AuthManager
from lojack_api.models import DeviceInfo, Location, VehicleInfo
from lojack_api.transport import AiohttpTransport


@pytest.fixture
def mock_transport():
    """Create a mock transport."""
    transport = MagicMock(spec=AiohttpTransport)
    transport.request = AsyncMock()
    transport.close = AsyncMock()
    transport.closed = False
    return transport


@pytest.fixture
def mock_auth():
    """Create a mock auth manager."""
    auth = MagicMock(spec=AuthManager)
    auth.login = AsyncMock(return_value="test-token")
    auth.get_token = AsyncMock(return_value="test-token")
    auth.is_authenticated = True
    auth.user_id = "user-123"
    return auth


@pytest.fixture
def sample_device_data():
    """Sample device data from API."""
    return {
        "id": "device-001",
        "name": "My Device",
        "type": "tracker",
        "status": "active",
        "last_seen": "2024-01-15T10:30:00Z",
    }


@pytest.fixture
def sample_vehicle_data():
    """Sample vehicle data from API."""
    return {
        "id": "vehicle-001",
        "name": "My Car",
        "type": "vehicle",
        "vin": "1HGCM82633A123456",
        "make": "Honda",
        "model": "Accord",
        "year": 2024,
        "license_plate": "ABC123",
        "status": "active",
        "last_seen": "2024-01-15T10:30:00Z",
    }


@pytest.fixture
def sample_location_data():
    """Sample location data from API.

    Note: accuracy of 25.0 is > 15, so it's treated as meters directly.
    Values <= 15 are treated as HDOP and multiplied by 5.
    """
    return {
        "latitude": 40.7128,
        "longitude": -74.0060,
        "accuracy": 25.0,  # Treated as meters (> HDOP threshold of 15)
        "speed": 25.0,
        "heading": 180,
        "timestamp": "2024-01-15T10:30:00Z",
        "address": "123 Main St, New York, NY",
    }


@pytest.fixture
def device_info(sample_device_data):
    """Create a DeviceInfo instance."""
    return DeviceInfo.from_api(sample_device_data)


@pytest.fixture
def vehicle_info(sample_vehicle_data):
    """Create a VehicleInfo instance."""
    return VehicleInfo.from_api(sample_vehicle_data)


@pytest.fixture
def location(sample_location_data):
    """Create a Location instance."""
    return Location.from_api(sample_location_data)
