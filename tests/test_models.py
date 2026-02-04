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

    def test_from_api_invalid_total(self):
        """Test parsing with invalid total amount."""
        data = {
            "id": "RO-003",
            "totalAmount": "not-a-number",
        }
        order = RepairOrder.from_api(data)
        assert order.id == "RO-003"
        assert order.total_amount is None


class TestLocationFromEvent:
    """Tests for Location.from_event method."""

    def test_basic_event_parsing(self):
        """Test basic event location parsing."""
        data = {
            "id": "event-123",
            "type": "SLEEP_ENTER",
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
            },
            "date": "2024-01-15T10:30:00Z",
            "speed": 25.0,
            "heading": 180,
        }
        loc = Location.from_event(data)
        assert loc.latitude == 32.8427
        assert loc.longitude == -97.0715
        assert loc.event_id == "event-123"
        assert loc.event_type == "SLEEP_ENTER"
        assert loc.speed == 25.0
        assert loc.heading == 180
        assert loc.timestamp is not None

    def test_event_with_nested_dict_address(self):
        """Test event with nested address object."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
                "address": {
                    "line1": "123 Main St",
                    "city": "Dallas",
                    "stateOrProvince": "TX",
                    "postalCode": "75201",
                },
            },
        }
        loc = Location.from_event(data)
        assert loc.address == "123 Main St, Dallas, TX 75201"

    def test_event_with_partial_address(self):
        """Test event with partial address (missing some fields)."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
                "address": {
                    "city": "Dallas",
                },
            },
        }
        loc = Location.from_event(data)
        assert loc.address == "Dallas"

    def test_event_with_string_address(self):
        """Test event with string address."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
            },
            "address": "123 Main St, Dallas, TX",
        }
        loc = Location.from_event(data)
        assert loc.address == "123 Main St, Dallas, TX"

    def test_event_with_formatted_address_fallback(self):
        """Test event uses formattedAddress as fallback."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
            },
            "formattedAddress": "123 Main St",
        }
        loc = Location.from_event(data)
        assert loc.address == "123 Main St"

    def test_event_with_telemetry_values(self):
        """Test event with all telemetry values."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "odometer": 51000.5,
            "batteryVoltage": 12.5,
            "engineHours": 1500.25,
            "distanceDriven": 45000.0,
            "signalStrength": 0.85,
            "gpsFixQuality": "GOOD",
        }
        loc = Location.from_event(data)
        assert loc.odometer == 51000.5
        assert loc.battery_voltage == 12.5
        assert loc.engine_hours == 1500.25
        assert loc.distance_driven == 45000.0
        assert loc.signal_strength == 0.85
        assert loc.gps_fix_quality == "GOOD"

    def test_event_with_invalid_odometer(self):
        """Test event with invalid odometer value."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "odometer": "not-a-number",
        }
        loc = Location.from_event(data)
        assert loc.odometer is None

    def test_event_with_invalid_battery_voltage(self):
        """Test event with invalid battery voltage value."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "batteryVoltage": "invalid",
        }
        loc = Location.from_event(data)
        assert loc.battery_voltage is None

    def test_event_with_invalid_engine_hours(self):
        """Test event with invalid engine hours value."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "engineHours": [],  # list instead of number
        }
        loc = Location.from_event(data)
        assert loc.engine_hours is None

    def test_event_with_invalid_distance_driven(self):
        """Test event with invalid distance driven value."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "distanceDriven": {"value": 100},  # dict instead of number
        }
        loc = Location.from_event(data)
        assert loc.distance_driven is None

    def test_event_with_invalid_signal_strength(self):
        """Test event with invalid signal strength value."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "signalStrength": "strong",  # string instead of number
        }
        loc = Location.from_event(data)
        assert loc.signal_strength is None

    def test_event_with_top_level_coordinates(self):
        """Test event with coordinates at top level."""
        data = {
            "lat": 32.8427,
            "longitude": -97.0715,
            "bearing": 90,
        }
        loc = Location.from_event(data)
        assert loc.latitude == 32.8427
        assert loc.longitude == -97.0715
        assert loc.heading == 90  # Uses bearing

    def test_event_with_alternate_timestamp_fields(self):
        """Test event with alternate timestamp field names."""
        data = {
            "location": {"lat": 32.8427, "lng": -97.0715},
            "eventDateTime": "2024-01-15T10:30:00Z",
        }
        loc = Location.from_event(data)
        assert loc.timestamp is not None

    def test_event_with_address_only_state_zip(self):
        """Test address with only state and zip."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
                "address": {
                    "stateOrProvince": "TX",
                    "postalCode": "75201",
                },
            },
        }
        loc = Location.from_event(data)
        assert loc.address == "TX 75201"

    def test_event_with_empty_address(self):
        """Test event with empty address object."""
        data = {
            "location": {
                "lat": 32.8427,
                "lng": -97.0715,
                "address": {},
            },
        }
        loc = Location.from_event(data)
        assert loc.address is None


class TestGeofenceEdgeCases:
    """Additional tests for Geofence edge cases."""

    def test_from_api_with_invalid_radius(self):
        """Test geofence with invalid radius value."""
        data = {
            "id": "geo-001",
            "name": "Test",
            "lat": 32.84,
            "lng": -97.07,
            "radius": "invalid",
        }
        geofence = Geofence.from_api(data)
        assert geofence.radius is None

    def test_from_api_with_nested_location_radius(self):
        """Test geofence with radius in nested location."""
        data = {
            "id": "geo-001",
            "location": {
                "coordinates": {"lat": 32.84, "lng": -97.07},
                "radius": 150.0,
            },
        }
        geofence = Geofence.from_api(data)
        assert geofence.radius == 150.0

    def test_from_api_with_string_address(self):
        """Test geofence with string address."""
        data = {
            "id": "geo-001",
            "lat": 32.84,
            "lng": -97.07,
            "address": "123 Main St",
        }
        geofence = Geofence.from_api(data)
        assert geofence.address == "123 Main St"

    def test_from_api_with_formatted_address(self):
        """Test geofence uses formattedAddress as fallback."""
        data = {
            "id": "geo-001",
            "lat": 32.84,
            "lng": -97.07,
            "formattedAddress": "123 Main St, City",
        }
        geofence = Geofence.from_api(data)
        assert geofence.address == "123 Main St, City"

    def test_to_api_payload_minimal(self):
        """Test minimal payload generation."""
        geofence = Geofence(id="geo-001", active=False)
        payload = geofence.to_api_payload()
        assert payload["active"] is False
        assert "name" not in payload
        assert "location" not in payload


class TestMaintenanceItemEdgeCases:
    """Additional tests for MaintenanceItem edge cases."""

    def test_from_api_with_invalid_mileage(self):
        """Test maintenance item with invalid mileage value."""
        data = {
            "name": "Oil Change",
            "mileageDue": "invalid",
        }
        item = MaintenanceItem.from_api(data)
        assert item.name == "Oil Change"
        assert item.mileage_due is None

    def test_from_api_with_invalid_months(self):
        """Test maintenance item with invalid months value."""
        data = {
            "name": "Oil Change",
            "monthsDue": "invalid",
        }
        item = MaintenanceItem.from_api(data)
        assert item.months_due is None

    def test_from_api_empty_name(self):
        """Test maintenance item with no name."""
        data = {"severity": "NORMAL"}
        item = MaintenanceItem.from_api(data)
        assert item.name == ""


class TestMaintenanceScheduleEdgeCases:
    """Additional tests for MaintenanceSchedule edge cases."""

    def test_from_api_with_services_key(self):
        """Test schedule with 'services' key."""
        data = {"services": [{"name": "Oil Change"}]}
        schedule = MaintenanceSchedule.from_api(data, vin="VIN123")
        assert len(schedule.items) == 1

    def test_from_api_with_maintenance_items_key(self):
        """Test schedule with 'maintenanceItems' key."""
        data = {"maintenanceItems": [{"name": "Oil Change"}]}
        schedule = MaintenanceSchedule.from_api(data)
        assert len(schedule.items) == 1

    def test_from_api_with_schedule_key(self):
        """Test schedule with 'schedule' key."""
        data = {"schedule": [{"name": "Oil Change"}]}
        schedule = MaintenanceSchedule.from_api(data)
        assert len(schedule.items) == 1

    def test_from_api_with_non_dict_items(self):
        """Test schedule ignores non-dict items."""
        data = {"items": [{"name": "Oil Change"}, "invalid", None]}
        schedule = MaintenanceSchedule.from_api(data)
        assert len(schedule.items) == 1


class TestVehicleInfoEdgeCases:
    """Additional tests for VehicleInfo edge cases."""

    def test_from_api_with_invalid_year(self):
        """Test vehicle with invalid year value."""
        data = {"id": "v1", "year": "invalid"}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.year is None

    def test_from_api_with_invalid_odometer(self):
        """Test vehicle with invalid odometer value."""
        data = {"id": "v1", "odometer": "invalid"}
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.odometer is None

    def test_from_api_with_attributes(self):
        """Test vehicle with nested attributes."""
        data = {
            "id": "v1",
            "attributes": {
                "vin": "ABC123",
                "make": "Honda",
                "model": "Civic",
                "name": "My Car",
                "type": "vehicle",
                "licensePlate": "XYZ789",
                "odometer": 50000,
            },
        }
        vehicle = VehicleInfo.from_api(data)
        assert vehicle.vin == "ABC123"
        assert vehicle.make == "Honda"
        assert vehicle.model == "Civic"
        assert vehicle.name == "My Car"
        assert vehicle.license_plate == "XYZ789"


class TestDeviceInfoEdgeCases:
    """Additional tests for DeviceInfo edge cases."""

    def test_from_api_with_attributes(self):
        """Test device with nested attributes."""
        data = {
            "id": "d1",
            "attributes": {
                "name": "My Device",
                "type": "tracker",
            },
        }
        device = DeviceInfo.from_api(data)
        assert device.name == "My Device"
        assert device.device_type == "tracker"

    def test_from_api_with_status_object(self):
        """Test device with status as nested object."""
        data = {
            "id": "d1",
            "status": {"status": "active"},
        }
        device = DeviceInfo.from_api(data)
        assert device.status == "active"

    def test_from_api_with_last_event_datetime(self):
        """Test device with lastEventDateTime field."""
        data = {
            "id": "d1",
            "lastEventDateTime": "2024-01-15T10:30:00Z",
        }
        device = DeviceInfo.from_api(data)
        assert device.last_seen is not None


class TestParseTimestampEdgeCases:
    """Additional tests for timestamp parsing edge cases."""

    def test_parse_timestamp_with_microseconds(self):
        """Test parsing timestamp with microseconds."""
        result = _parse_timestamp("2024-01-15T10:30:00.123456Z")
        assert result is not None
        assert result.year == 2024

    def test_parse_timestamp_with_timezone_offset(self):
        """Test parsing timestamp with timezone offset."""
        result = _parse_timestamp("2024-01-15T10:30:00+0000")
        assert result is not None

    def test_parse_timestamp_simple_format(self):
        """Test parsing simple datetime format."""
        result = _parse_timestamp("2024-01-15 10:30:00")
        assert result is not None
        assert result.year == 2024

    def test_parse_timestamp_invalid_unix(self):
        """Test parsing invalid unix timestamp."""
        # Very large value that could cause overflow
        result = _parse_timestamp(99999999999999999)
        assert result is None

    def test_parse_timestamp_fromisoformat_fallback(self):
        """Test fromisoformat fallback for non-standard format."""
        result = _parse_timestamp("2024-01-15T10:30:00.123+00:00")
        assert result is not None


class TestParseGpsAccuracyEdgeCases:
    """Additional tests for GPS accuracy parsing edge cases."""

    def test_hdop_string_positive(self):
        """Test positive HDOP as string."""
        result = _parse_gps_accuracy(None, hdop="5.0")
        assert result == 25.0

    def test_hdop_string_negative(self):
        """Test negative HDOP as string."""
        result = _parse_gps_accuracy(None, hdop="-5")
        assert result is None

    def test_quality_moderate(self):
        """Test MODERATE quality string."""
        result = _parse_gps_accuracy(None, None, "MODERATE")
        assert result == 25.0

    def test_quality_fair(self):
        """Test FAIR quality string."""
        result = _parse_gps_accuracy(None, None, "FAIR")
        assert result == 25.0

    def test_quality_bad(self):
        """Test BAD quality string."""
        result = _parse_gps_accuracy(None, None, "BAD")
        assert result == 100.0

    def test_quality_very_poor(self):
        """Test VERY_POOR quality string."""
        result = _parse_gps_accuracy(None, None, "VERY_POOR")
        assert result == 100.0

    def test_quality_no_fix(self):
        """Test NO_FIX quality string."""
        result = _parse_gps_accuracy(None, None, "NO_FIX")
        assert result == 200.0

    def test_quality_with_space(self):
        """Test quality string with space."""
        result = _parse_gps_accuracy(None, None, "VERY POOR")
        assert result == 100.0
