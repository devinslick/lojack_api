"""Tests for device wrapper classes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lojack_api.device import Device, Vehicle
from lojack_api.models import Location


class TestDevice:
    """Tests for Device wrapper."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        client.get_current_location = AsyncMock(return_value=None)
        client.get_locations = AsyncMock(return_value=[])
        client.send_command = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def device(self, mock_client, device_info):
        """Create a Device instance."""
        return Device(mock_client, device_info)

    def test_properties(self, device, device_info):
        """Test device properties."""
        assert device.id == device_info.id
        assert device.name == device_info.name
        assert device.info == device_info

    @pytest.mark.asyncio
    async def test_refresh(self, device, mock_client, location):
        """Test refreshing device location."""
        # get_current_location returns None, so falls back to get_locations
        mock_client.get_current_location.return_value = None
        mock_client.get_locations.return_value = [location]

        await device.refresh(force=True)

        assert device.cached_location == location
        assert device.last_refresh is not None
        mock_client.get_current_location.assert_called_once()
        mock_client.get_locations.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_uses_current_location(self, device, mock_client, location):
        """Test refreshing uses get_current_location and enriches with event telemetry."""
        mock_client.get_current_location.return_value = location
        # Events are always fetched to enrich telemetry
        mock_client.get_locations.return_value = []

        await device.refresh(force=True)

        assert device.cached_location == location
        assert device.last_refresh is not None
        mock_client.get_current_location.assert_called_once()
        # get_locations is always called to fetch telemetry from events
        mock_client.get_locations.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_enriches_with_event_telemetry(self, device, mock_client):
        """Test that refresh enriches location with telemetry from events."""
        # Current location has coordinates but no telemetry
        current_loc = Location.from_api({"lat": 40.7128, "lng": -74.006})

        # Event has telemetry data
        event_loc = Location(
            latitude=40.7128,
            longitude=-74.006,
            speed=25.0,
            battery_voltage=12.5,
            signal_strength=0.8,
            gps_fix_quality="GOOD",
        )

        mock_client.get_current_location.return_value = current_loc
        mock_client.get_locations.return_value = [event_loc]

        await device.refresh(force=True)

        # Verify telemetry was enriched from event
        assert device.cached_location.speed == 25.0
        assert device.cached_location.battery_voltage == 12.5
        assert device.cached_location.signal_strength == 0.8
        assert device.cached_location.gps_fix_quality == "GOOD"

    @pytest.mark.asyncio
    async def test_refresh_skips_if_cached(self, device, mock_client, location):
        """Test refresh skips if cached."""
        device._cached_location = location

        await device.refresh()

        mock_client.get_locations.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_location(self, device, mock_client, location):
        """Test getting device location."""
        mock_client.get_current_location.return_value = location
        mock_client.get_locations.return_value = []  # No events for telemetry

        result = await device.get_location()

        assert result == location

    @pytest.mark.asyncio
    async def test_get_location_force(self, device, mock_client, location):
        """Test force refreshing location."""
        old_location = Location.from_api({"latitude": 0, "longitude": 0})
        device._cached_location = old_location

        mock_client.get_current_location.return_value = location
        mock_client.get_locations.return_value = []  # No events for telemetry

        result = await device.get_location(force=True)

        assert result == location
        mock_client.get_current_location.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_history(self, device, mock_client, location):
        """Test getting location history."""
        mock_client.get_locations.return_value = [location, location]

        history = []
        async for loc in device.get_history(limit=10):
            history.append(loc)

        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_send_command(self, device, mock_client):
        """Test sending a command."""
        result = await device.send_command("test_command")

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "test_command")

    def test_repr(self, device):
        """Test string representation."""
        repr_str = repr(device)
        assert "Device" in repr_str
        assert device.id in repr_str


class TestVehicle:
    """Tests for Vehicle wrapper."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        client.get_current_location = AsyncMock(return_value=None)
        client.get_locations = AsyncMock(return_value=[])
        client.send_command = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def vehicle(self, mock_client, vehicle_info):
        """Create a Vehicle instance."""
        return Vehicle(mock_client, vehicle_info)

    def test_vehicle_properties(self, vehicle, vehicle_info):
        """Test vehicle-specific properties."""
        assert vehicle.vin == vehicle_info.vin
        assert vehicle.make == vehicle_info.make
        assert vehicle.model == vehicle_info.model
        assert vehicle.year == vehicle_info.year
        assert vehicle.license_plate == vehicle_info.license_plate

    def test_repr(self, vehicle):
        """Test string representation."""
        repr_str = repr(vehicle)
        assert "Vehicle" in repr_str
        assert vehicle.id in repr_str
        assert vehicle.vin in repr_str
