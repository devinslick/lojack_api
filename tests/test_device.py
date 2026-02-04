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


class TestDeviceGeofences:
    """Tests for Device geofence methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        client.list_geofences = AsyncMock(return_value=[])
        client.get_geofence = AsyncMock(return_value=None)
        client.create_geofence = AsyncMock(return_value=None)
        client.update_geofence = AsyncMock(return_value=True)
        client.delete_geofence = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def device(self, mock_client, device_info):
        """Create a Device instance."""
        return Device(mock_client, device_info)

    @pytest.mark.asyncio
    async def test_list_geofences(self, device, mock_client):
        """Test listing geofences."""
        await device.list_geofences()
        mock_client.list_geofences.assert_called_once_with(device.id)

    @pytest.mark.asyncio
    async def test_get_geofence(self, device, mock_client):
        """Test getting a geofence."""
        await device.get_geofence("geo-1")
        mock_client.get_geofence.assert_called_once_with(device.id, "geo-1")

    @pytest.mark.asyncio
    async def test_create_geofence(self, device, mock_client):
        """Test creating a geofence."""
        await device.create_geofence(
            name="Home", latitude=32.84, longitude=-97.07, radius=100.0
        )
        mock_client.create_geofence.assert_called_once_with(
            device.id,
            name="Home",
            latitude=32.84,
            longitude=-97.07,
            radius=100.0,
            address=None,
        )

    @pytest.mark.asyncio
    async def test_update_geofence(self, device, mock_client):
        """Test updating a geofence."""
        await device.update_geofence("geo-1", name="Updated")
        mock_client.update_geofence.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_geofence(self, device, mock_client):
        """Test deleting a geofence."""
        await device.delete_geofence("geo-1")
        mock_client.delete_geofence.assert_called_once_with(device.id, "geo-1")


class TestDeviceLocationMethods:
    """Tests for Device location methods."""

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

    @pytest.mark.asyncio
    async def test_request_location_update(self, device, mock_client):
        """Test requesting location update."""
        result = await device.request_location_update()
        assert result is True
        mock_client.send_command.assert_called_once_with(device.id, "locate")

    @pytest.mark.asyncio
    async def test_request_fresh_location(self, device, mock_client, location):
        """Test requesting fresh location."""
        mock_client.get_current_location.return_value = location

        baseline_ts = await device.request_fresh_location()

        assert baseline_ts == location.timestamp
        mock_client.send_command.assert_called_once_with(device.id, "locate")

    @pytest.mark.asyncio
    async def test_request_fresh_location_no_location(self, device, mock_client):
        """Test requesting fresh location when no current location."""
        mock_client.get_current_location.return_value = None

        baseline_ts = await device.request_fresh_location()

        assert baseline_ts is None
        mock_client.send_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_fresh_location_command_fails(self, device, mock_client, location):
        """Test requesting fresh location when command fails."""
        mock_client.get_current_location.return_value = location
        mock_client.send_command.side_effect = Exception("Command failed")

        # Should not raise, just return baseline
        baseline_ts = await device.request_fresh_location()

        assert baseline_ts == location.timestamp

    def test_location_timestamp(self, device, location):
        """Test location_timestamp property."""
        device._cached_location = location
        assert device.location_timestamp == location.timestamp

    def test_location_timestamp_none(self, device):
        """Test location_timestamp when no cached location."""
        assert device.location_timestamp is None


class TestDeviceUpdate:
    """Tests for Device update method."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        client.update_asset = AsyncMock(return_value=True)
        return client

    @pytest.fixture
    def device(self, mock_client, device_info):
        """Create a Device instance."""
        return Device(mock_client, device_info)

    @pytest.mark.asyncio
    async def test_update(self, device, mock_client):
        """Test updating device."""
        result = await device.update(name="New Name")

        assert result is True
        mock_client.update_asset.assert_called_once_with(
            device.id, name="New Name", color=None
        )


class TestVehicle:
    """Tests for Vehicle wrapper."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock client."""
        client = MagicMock()
        client.get_current_location = AsyncMock(return_value=None)
        client.get_locations = AsyncMock(return_value=[])
        client.send_command = AsyncMock(return_value=True)
        client.update_asset = AsyncMock(return_value=True)
        client.get_maintenance_schedule = AsyncMock(return_value=None)
        client.get_repair_orders = AsyncMock(return_value=[])
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

    @pytest.mark.asyncio
    async def test_update(self, vehicle, mock_client):
        """Test updating vehicle."""
        result = await vehicle.update(name="New Name", odometer=50000.0)

        assert result is True
        mock_client.update_asset.assert_called_once()
        call_args = mock_client.update_asset.call_args
        assert call_args[1]["name"] == "New Name"
        assert call_args[1]["odometer"] == 50000.0

    @pytest.mark.asyncio
    async def test_get_maintenance_schedule(self, vehicle, mock_client):
        """Test getting maintenance schedule."""
        await vehicle.get_maintenance_schedule()
        mock_client.get_maintenance_schedule.assert_called_once_with(vehicle.vin)

    @pytest.mark.asyncio
    async def test_get_maintenance_schedule_no_vin(self, mock_client, vehicle_info):
        """Test getting maintenance schedule without VIN."""
        vehicle_info.vin = None
        vehicle = Vehicle(mock_client, vehicle_info)

        result = await vehicle.get_maintenance_schedule()

        assert result is None
        mock_client.get_maintenance_schedule.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_repair_orders(self, vehicle, mock_client):
        """Test getting repair orders."""
        await vehicle.get_repair_orders()
        mock_client.get_repair_orders.assert_called_once_with(
            vin=vehicle.vin, asset_id=vehicle.id
        )
