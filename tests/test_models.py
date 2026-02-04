"""Tests for data models."""

from datetime import datetime, timezone

from lojack_api.models import (
    DeviceInfo,
    Geofence,
    Location,
    MaintenanceItem,
    MaintenanceSchedule,
    RepairOrder,
    VehicleInfo,
    _parse_gps_accuracy,
    _parse_timestamp,
)


class TestParseGpsAccuracy:
    """Tests for GPS accuracy parsing and conversion to meters."""

    def test_hdop_conversion(self):
        """Test HDOP values are converted to meters (multiplied by 5)."""
        # HDOP of 2 should give 10 meters
        assert _parse_gps_accuracy(2.0) == 10.0
        # HDOP of 1 should give 5 meters
        assert _parse_gps_accuracy(1.0) == 5.0

    def test_large_value_treated_as_meters(self):
        """Test values > 15 are treated as meters directly."""
        assert _parse_gps_accuracy(25.0) == 25.0
        assert _parse_gps_accuracy(100.0) == 100.0

    def test_explicit_hdop_field(self):
        """Test explicit hdop parameter is always converted."""
        # Even if accuracy is None, hdop should work
        assert _parse_gps_accuracy(None, hdop=2.0) == 10.0
        # hdop takes precedence format-wise (always converted)
        assert _parse_gps_accuracy(None, hdop=20.0) == 100.0

    def test_gps_quality_string_good(self):
        """Test GOOD quality string maps to 10 meters."""
        assert _parse_gps_accuracy("GOOD") == 10.0
        assert _parse_gps_accuracy("good") == 10.0

    def test_gps_quality_string_poor(self):
        """Test POOR quality string maps to 50 meters."""
        assert _parse_gps_accuracy("POOR") == 50.0

    def test_gps_quality_string_excellent(self):
        """Test EXCELLENT quality string maps to 5 meters."""
        assert _parse_gps_accuracy("EXCELLENT") == 5.0

    def test_gps_quality_fallback(self):
        """Test gps_quality parameter used as fallback."""
        assert _parse_gps_accuracy(None, None, "GOOD") == 10.0
        assert _parse_gps_accuracy(None, None, "POOR") == 50.0

    def test_numeric_string(self):
        """Test numeric strings are parsed correctly."""
        assert _parse_gps_accuracy("2.0") == 10.0  # Treated as HDOP
        assert _parse_gps_accuracy("25.0") == 25.0  # Treated as meters

    def test_none_returns_none(self):
        """Test that all None inputs return None."""
        assert _parse_gps_accuracy(None) is None
        assert _parse_gps_accuracy(None, None, None) is None

    def test_unknown_quality_string(self):
        """Test unknown quality strings fall through to gps_quality param."""
        # Unknown string in accuracy, but valid gps_quality
        assert _parse_gps_accuracy("UNKNOWN", None, "GOOD") == 10.0
        # Unknown string everywhere returns None
        assert _parse_gps_accuracy("UNKNOWN", None, "UNKNOWN") is None

    def test_zero_and_negative_values_return_none(self):
        """Zero or negative HDOP/accuracy should be treated as missing."""
        # Explicit hdop of 0 should be ignored
        assert _parse_gps_accuracy(None, hdop=0) is None
        # Numeric accuracy of 0 should be ignored
        assert _parse_gps_accuracy(0) is None
        # Negative values should also be ignored
        assert _parse_gps_accuracy(-1) is None
        assert _parse_gps_accuracy(None, hdop="-2") is None


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
        assert loc.accuracy == 25.0  # > 15, so treated as meters directly
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


class TestGeofence:
    """Tests for Geofence model."""

    def test_from_api_basic(self):
        """Test basic geofence parsing."""
        data = {
            "id": "geo-001",
            "name": "Home",
            "location": {
                "coordinates": {"lat": 32.8427, "lng": -97.0715},
                "radius": 100.0,
            },
            "active": True,
        }
        geofence = Geofence.from_api(data, asset_id="asset-001")
        assert geofence.id == "geo-001"
        assert geofence.name == "Home"
        assert geofence.latitude == 32.8427
        assert geofence.longitude == -97.0715
        assert geofence.radius == 100.0
        assert geofence.active is True
        assert geofence.asset_id == "asset-001"

    def test_from_api_alternate_keys(self):
        """Test parsing with alternate key names."""
        data = {
            "geofenceId": "geo-002",
            "label": "Work",
            "lat": 40.7128,
            "longitude": -74.006,
            "radius": "200",
            "active": False,
        }
        geofence = Geofence.from_api(data)
        assert geofence.id == "geo-002"
        assert geofence.name == "Work"
        assert geofence.latitude == 40.7128
        assert geofence.longitude == -74.006
        assert geofence.radius == 200.0
        assert geofence.active is False

    def test_from_api_with_address(self):
        """Test parsing with nested address."""
        data = {
            "id": "geo-003",
            "name": "Office",
            "location": {
                "coordinates": {"lat": 37.7749, "lng": -122.4194},
                "address": {
                    "line1": "123 Market St",
                    "city": "San Francisco",
                    "stateOrProvince": "CA",
                    "postalCode": "94105",
                },
            },
        }
        geofence = Geofence.from_api(data)
        assert geofence.address == "123 Market St, San Francisco, CA 94105"

    def test_to_api_payload(self):
        """Test converting to API payload."""
        geofence = Geofence(
            id="geo-001",
            name="Test",
            latitude=32.8427,
            longitude=-97.0715,
            radius=150.0,
            address="123 Main St",
            active=True,
        )
        payload = geofence.to_api_payload()
        assert payload["name"] == "Test"
        assert payload["location"]["coordinates"]["lat"] == 32.8427
        assert payload["location"]["coordinates"]["lng"] == -97.0715
        assert payload["location"]["radius"] == 150.0
        assert payload["active"] is True


class TestMaintenanceItem:
    """Tests for MaintenanceItem model."""

    def test_from_api_basic(self):
        """Test basic maintenance item parsing."""
        data = {
            "name": "Oil Change",
            "description": "Replace engine oil and filter",
            "severity": "NORMAL",
            "mileageDue": 55000,
            "monthsDue": 6,
            "action": "Schedule service",
        }
        item = MaintenanceItem.from_api(data)
        assert item.name == "Oil Change"
        assert item.description == "Replace engine oil and filter"
        assert item.severity == "NORMAL"
        assert item.mileage_due == 55000.0
        assert item.months_due == 6
        assert item.action == "Schedule service"

    def test_from_api_alternate_keys(self):
        """Test parsing with alternate key names."""
        data = {
            "serviceName": "Tire Rotation",
            "serviceDescription": "Rotate tires",
            "level": "WARNING",
            "dueMileage": 60000,
            "dueMonths": 12,
            "recommendedAction": "Visit dealer",
        }
        item = MaintenanceItem.from_api(data)
        assert item.name == "Tire Rotation"
        assert item.description == "Rotate tires"
        assert item.severity == "WARNING"
        assert item.mileage_due == 60000.0
        assert item.months_due == 12
        assert item.action == "Visit dealer"


class TestMaintenanceSchedule:
    """Tests for MaintenanceSchedule model."""

    def test_from_api_basic(self):
        """Test basic maintenance schedule parsing."""
        data = {
            "vin": "1HGCM82633A123456",
            "items": [
                {"name": "Oil Change", "mileageDue": 55000},
                {"name": "Tire Rotation", "mileageDue": 60000},
            ],
        }
        schedule = MaintenanceSchedule.from_api(data)
        assert schedule.vin == "1HGCM82633A123456"
        assert len(schedule.items) == 2
        assert schedule.items[0].name == "Oil Change"
        assert schedule.items[1].name == "Tire Rotation"

    def test_from_api_with_vin_param(self):
        """Test VIN passed as parameter."""
        data = {"services": [{"name": "Brake Inspection"}]}
        schedule = MaintenanceSchedule.from_api(data, vin="VIN123")
        assert schedule.vin == "VIN123"
        assert len(schedule.items) == 1


class TestRepairOrder:
    """Tests for RepairOrder model."""

    def test_from_api_basic(self):
        """Test basic repair order parsing."""
        data = {
            "id": "RO-001",
            "vin": "1HGCM82633A123456",
            "assetId": "asset-001",
            "status": "CLOSED",
            "openDate": "2024-01-15T10:30:00Z",
            "closeDate": "2024-01-16T15:00:00Z",
            "description": "Oil change and inspection",
            "totalAmount": 75.50,
        }
        order = RepairOrder.from_api(data)
        assert order.id == "RO-001"
        assert order.vin == "1HGCM82633A123456"
        assert order.asset_id == "asset-001"
        assert order.status == "CLOSED"
        assert order.open_date is not None
        assert order.close_date is not None
        assert order.description == "Oil change and inspection"
        assert order.total_amount == 75.50

    def test_from_api_alternate_keys(self):
        """Test parsing with alternate key names."""
        data = {
            "repairOrderId": "RO-002",
            "status": "OPEN",
            "createdDate": "2024-02-01T09:00:00Z",
            "notes": "Brake service",
            "total": "125.00",
        }
        order = RepairOrder.from_api(data)
        assert order.id == "RO-002"
        assert order.status == "OPEN"
        assert order.open_date is not None
        assert order.description == "Brake service"
        assert order.total_amount == 125.0
