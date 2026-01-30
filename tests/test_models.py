"""Tests for data models."""

from datetime import datetime, timezone

from lojack_api.models import DeviceInfo, Location, VehicleInfo, _parse_timestamp


class TestParseTimestamp:
    """Tests for timestamp parsing."""

    def test_parse_iso_string(self):
        """Test parsing ISO format string."""
        result = _parse_timestamp("2024-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_iso_string_with_timezone(self):
        """Test parsing ISO format with timezone."""
        result = _parse_timestamp("2024-01-15T10:30:00+00:00")
        assert result is not None
        assert result.tzinfo is not None

    def test_parse_unix_timestamp_seconds(self):
        """Test parsing Unix timestamp in seconds."""
        result = _parse_timestamp(1705315800)  # 2024-01-15 10:30:00 UTC
        assert result is not None
        assert result.year == 2024

    def test_parse_unix_timestamp_milliseconds(self):
        """Test parsing Unix timestamp in milliseconds."""
        result = _parse_timestamp(1705315800000)
        assert result is not None
        assert result.year == 2024

    def test_parse_datetime_passthrough(self):
        """Test that datetime objects pass through."""
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _parse_timestamp(dt)
        assert result == dt

    def test_parse_none(self):
        """Test that None returns None."""
        assert _parse_timestamp(None) is None

    def test_parse_invalid_string(self):
        """Test that invalid strings return None."""
        assert _parse_timestamp("not a date") is None


class TestLocation:
    """Tests for Location model."""

    def test_from_api_basic(self, sample_location_data):
        """Test basic location parsing."""
        loc = Location.from_api(sample_location_data)
        assert loc.latitude == 40.7128
        assert loc.longitude == -74.0060
        assert loc.accuracy == 10.5
        assert loc.speed == 25.0
        assert loc.heading == 180
        assert loc.address == "123 Main St, New York, NY"
        assert loc.timestamp is not None

    def test_from_api_alternate_keys(self):
        """Test parsing with alternate key names."""
        data = {
            "lat": 40.7128,
            "lng": -74.0060,
            "bearing": 90,
            "time": "2024-01-15T10:30:00Z",
        }
        loc = Location.from_api(data)
        assert loc.latitude == 40.7128
        assert loc.longitude == -74.0060
        assert loc.heading == 90
        assert loc.timestamp is not None

    def test_from_api_empty(self):
        """Test parsing empty data."""
        loc = Location.from_api({})
        assert loc.latitude is None
        assert loc.longitude is None
        assert loc.raw == {}


class TestDeviceInfo:
    """Tests for DeviceInfo model."""

    def test_from_api_basic(self, sample_device_data):
        """Test basic device parsing."""
        device = DeviceInfo.from_api(sample_device_data)
        assert device.id == "device-001"
        assert device.name == "My Device"
        assert device.device_type == "tracker"
        assert device.status == "active"
        assert device.last_seen is not None

    def test_from_api_alternate_keys(self):
        """Test parsing with alternate key names."""
        data = {
            "device_id": "dev-123",
            "device_name": "Test Device",
            "lastSeen": "2024-01-15T10:30:00Z",
        }
        device = DeviceInfo.from_api(data)
        assert device.id == "dev-123"
        assert device.name == "Test Device"
        assert device.last_seen is not None

    def test_from_api_empty(self):
        """Test parsing with minimal data."""
        device = DeviceInfo.from_api({})
        assert device.id == ""
        assert device.name is None


class TestVehicleInfo:
    """Tests for VehicleInfo model."""

    def test_from_api_basic(self, sample_vehicle_data):
        """Test basic vehicle parsing."""
        vehicle = VehicleInfo.from_api(sample_vehicle_data)
        assert vehicle.id == "vehicle-001"
        assert vehicle.name == "My Car"
        assert vehicle.vin == "1HGCM82633A123456"
        assert vehicle.make == "Honda"
        assert vehicle.model == "Accord"
        assert vehicle.year == 2024
        assert vehicle.license_plate == "ABC123"

    def test_from_api_year_parsing(self):
        """Test year parsing as string."""
        data = {"id": "v1", "year": "2024"}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.year == 2024

    def test_from_api_odometer_parsing(self):
        """Test odometer parsing."""
        data = {"id": "v1", "odometer": "15000.5"}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.odometer == 15000.5

    def test_from_api_mileage_alternate(self):
        """Test odometer parsing from mileage key."""
        data = {"id": "v1", "mileage": 20000}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.odometer == 20000.0

    def test_from_api_license_plate_alternate(self):
        """Test license plate parsing from camelCase."""
        data = {"id": "v1", "licensePlate": "XYZ789"}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.license_plate == "XYZ789"
