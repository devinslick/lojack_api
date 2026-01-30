"""Data models for LoJack API responses.

These are simple dataclasses representing the raw data from the API.
For objects with methods (refresh, lock, etc.), see device.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Location:
    """A single location point from the API."""

    latitude: float | None = None
    longitude: float | None = None
    timestamp: datetime | None = None
    accuracy: float | None = None
    speed: float | None = None
    heading: float | None = None
    address: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Location:
        """Parse a location from API response data."""
        loc = cls(raw=data)

        # Handle nested coordinates (Spireon format)
        coords = data.get("coordinates", {})

        loc.latitude = (
            data.get("latitude")
            or data.get("lat")
            or coords.get("latitude")
            or coords.get("lat")
        )
        loc.longitude = (
            data.get("longitude")
            or data.get("lng")
            or data.get("lon")
            or coords.get("longitude")
            or coords.get("lng")
        )
        loc.accuracy = data.get("accuracy") or data.get("hdop")
        loc.speed = data.get("speed")
        loc.heading = data.get("heading") or data.get("bearing") or data.get("course")
        loc.address = data.get("address") or data.get("formattedAddress")

        # Parse timestamp - try multiple formats
        ts = (
            data.get("timestamp")
            or data.get("time")
            or data.get("recorded_at")
            or data.get("eventDateTime")
            or data.get("dateTime")
        )
        if ts:
            loc.timestamp = _parse_timestamp(ts)

        return loc

    @classmethod
    def from_event(cls, event_data: dict[str, Any]) -> Location:
        """Parse a location from a Spireon event.

        Spireon events have a nested structure:
        {
            "location": {"lat": 40.7128, "lng": -74.0060},
            "heading": 180,
            "speed": 35,
            "date": "2024-01-15T12:00:00.000+0000",
            ...
        }
        """
        loc = cls(raw=event_data)

        # Get nested location object
        location_data = event_data.get("location", {})

        # Parse coordinates from nested location or top-level
        loc.latitude = (
            location_data.get("lat")
            or location_data.get("latitude")
            or event_data.get("lat")
            or event_data.get("latitude")
        )
        loc.longitude = (
            location_data.get("lng")
            or location_data.get("lon")
            or location_data.get("longitude")
            or event_data.get("lng")
            or event_data.get("lon")
            or event_data.get("longitude")
        )

        # Speed and heading are at top level in events
        loc.speed = event_data.get("speed")
        loc.heading = (
            event_data.get("heading")
            or event_data.get("bearing")
            or event_data.get("course")
        )
        loc.accuracy = event_data.get("accuracy") or event_data.get("hdop")
        loc.address = event_data.get("address") or event_data.get("formattedAddress")

        # Parse timestamp - events use "date" field
        ts = (
            event_data.get("date")
            or event_data.get("eventDateTime")
            or event_data.get("dateTime")
            or event_data.get("timestamp")
        )
        if ts:
            loc.timestamp = _parse_timestamp(ts)

        return loc


@dataclass
class DeviceInfo:
    """Basic device information from the API."""

    id: str
    name: str | None = None
    device_type: str | None = None
    status: str | None = None
    last_seen: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> DeviceInfo:
        """Parse device info from API response data."""
        # Handle Spireon's nested "attributes" structure
        attrs = data.get("attributes", {})
        status_obj = data.get("status", {})

        device = cls(
            id=data.get("id") or data.get("device_id") or data.get("assetId") or "",
            name=data.get("name") or attrs.get("name") or data.get("device_name"),
            device_type=data.get("type") or attrs.get("type") or data.get("device_type"),
            status=(
                status_obj.get("status")
                if isinstance(status_obj, dict)
                else data.get("status")
            ),
            raw=data,
        )

        ts = (
            data.get("last_seen")
            or data.get("lastSeen")
            or data.get("last_updated")
            or data.get("lastEventDateTime")
        )
        if ts:
            device.last_seen = _parse_timestamp(ts)

        return device


@dataclass
class VehicleInfo(DeviceInfo):
    """Vehicle-specific information extending DeviceInfo."""

    vin: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    license_plate: str | None = None
    odometer: float | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> VehicleInfo:
        """Parse vehicle info from API response data."""
        # Handle Spireon's nested "attributes" structure
        attrs = data.get("attributes", {})
        status_obj = data.get("status", {})

        vehicle = cls(
            id=(
                data.get("id")
                or data.get("device_id")
                or data.get("vehicle_id")
                or data.get("assetId")
                or ""
            ),
            name=data.get("name") or attrs.get("name") or data.get("vehicle_name"),
            device_type=(
                data.get("type")
                or attrs.get("type")
                or data.get("device_type")
                or "vehicle"
            ),
            status=(
                status_obj.get("status")
                if isinstance(status_obj, dict)
                else data.get("status")
            ),
            raw=data,
            vin=data.get("vin") or attrs.get("vin"),
            make=data.get("make") or attrs.get("make"),
            model=data.get("model") or attrs.get("model"),
            license_plate=(
                data.get("license_plate")
                or data.get("licensePlate")
                or attrs.get("licensePlate")
                or attrs.get("license_plate")
            ),
        )

        # Parse year from either top-level or attributes
        year = data.get("year") or attrs.get("year")
        if year is not None:
            try:
                vehicle.year = int(year)
            except (ValueError, TypeError):
                pass

        # Parse odometer from either top-level or attributes
        odometer = data.get("odometer") or data.get("mileage") or attrs.get("odometer")
        if odometer is not None:
            try:
                vehicle.odometer = float(odometer)
            except (ValueError, TypeError):
                pass

        ts = (
            data.get("last_seen")
            or data.get("lastSeen")
            or data.get("last_updated")
            or data.get("lastEventDateTime")
        )
        if ts:
            vehicle.last_seen = _parse_timestamp(ts)

        return vehicle


def _parse_timestamp(ts: Any) -> datetime | None:
    """Parse various timestamp formats into datetime."""
    if ts is None:
        return None

    if isinstance(ts, datetime):
        return ts

    if isinstance(ts, (int, float)):
        # Unix timestamp (seconds or milliseconds)
        if ts > 1e12:  # Likely milliseconds
            ts = ts / 1000
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError):
            return None

    if isinstance(ts, str):
        # Try ISO format first
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                dt = datetime.strptime(ts, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        # Try fromisoformat as fallback
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt
        except ValueError:
            pass

    return None
