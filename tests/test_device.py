"""Tests for device wrapper classes."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from lojack_api.device import Device, Vehicle, _is_valid_passcode, _sanitize_message
from lojack_api.exceptions import InvalidParameterError
from lojack_api.models import Location


class TestSanitizeMessage:
    """Tests for message sanitization."""

    def test_basic_message(self):
        """Test basic message passes through."""
        assert _sanitize_message("Hello World") == "Hello World"

    def test_removes_dangerous_chars(self):
        """Test dangerous characters are removed."""
        result = _sanitize_message('Hello "World"; DROP TABLE')
        assert '"' not in result
        assert ";" not in result

    def test_normalizes_whitespace(self):
        """Test whitespace is normalized."""
        result = _sanitize_message("Hello   \n  World")
        assert result == "Hello World"

    def test_truncates_long_message(self):
        """Test long messages are truncated."""
        long_msg = "A" * 200
        result = _sanitize_message(long_msg)
        assert len(result) == 120

    def test_custom_max_length(self):
        """Test custom max length."""
        result = _sanitize_message("AAAAAAAAAA", max_length=5)
        assert len(result) == 5


class TestIsValidPasscode:
    """Tests for passcode validation."""

    def test_valid_alphanumeric(self):
        """Test valid alphanumeric passcodes."""
        assert _is_valid_passcode("abc123")
        assert _is_valid_passcode("ABC123")
        assert _is_valid_passcode("1234567890")

    def test_invalid_with_spaces(self):
        """Test passcodes with spaces are invalid."""
        assert not _is_valid_passcode("abc 123")

    def test_invalid_with_special_chars(self):
        """Test passcodes with special characters are invalid."""
        assert not _is_valid_passcode("abc@123")
        assert not _is_valid_passcode("abc!123")

    def test_invalid_with_unicode(self):
        """Test passcodes with unicode are invalid."""
        assert not _is_valid_passcode("abc123\u00e9")


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

    @pytest.mark.asyncio
    async def test_lock(self, device, mock_client):
        """Test lock command."""
        result = await device.lock()

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "lock")

    @pytest.mark.asyncio
    async def test_lock_with_message(self, device, mock_client):
        """Test lock command with message."""
        result = await device.lock(message="Please return")

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "lock Please return")

    @pytest.mark.asyncio
    async def test_lock_invalid_passcode(self, device, mock_client):
        """Test lock with invalid passcode."""
        with pytest.raises(InvalidParameterError, match="passcode"):
            await device.lock(passcode="invalid passcode!")

    @pytest.mark.asyncio
    async def test_unlock(self, device, mock_client):
        """Test unlock command."""
        result = await device.unlock()

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "unlock")

    @pytest.mark.asyncio
    async def test_ring(self, device, mock_client):
        """Test ring command."""
        result = await device.ring()

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "ring")

    @pytest.mark.asyncio
    async def test_ring_with_duration(self, device, mock_client):
        """Test ring command with duration."""
        result = await device.ring(duration=30)

        assert result is True
        mock_client.send_command.assert_called_with(device.id, "ring 30")

    @pytest.mark.asyncio
    async def test_ring_invalid_duration(self, device, mock_client):
        """Test ring with invalid duration."""
        with pytest.raises(InvalidParameterError, match="duration"):
            await device.ring(duration=500)

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

    @pytest.mark.asyncio
    async def test_start_engine(self, vehicle, mock_client):
        """Test start engine command."""
        result = await vehicle.start_engine()

        assert result is True
        mock_client.send_command.assert_called_with(vehicle.id, "start")

    @pytest.mark.asyncio
    async def test_stop_engine(self, vehicle, mock_client):
        """Test stop engine command."""
        result = await vehicle.stop_engine()

        assert result is True
        mock_client.send_command.assert_called_with(vehicle.id, "stop")

    @pytest.mark.asyncio
    async def test_honk_horn(self, vehicle, mock_client):
        """Test honk horn command."""
        result = await vehicle.honk_horn()

        assert result is True
        mock_client.send_command.assert_called_with(vehicle.id, "honk")

    @pytest.mark.asyncio
    async def test_flash_lights(self, vehicle, mock_client):
        """Test flash lights command."""
        result = await vehicle.flash_lights()

        assert result is True
        mock_client.send_command.assert_called_with(vehicle.id, "flash")

    def test_repr(self, vehicle):
        """Test string representation."""
        repr_str = repr(vehicle)
        assert "Vehicle" in repr_str
        assert vehicle.id in repr_str
        assert vehicle.vin in repr_str
