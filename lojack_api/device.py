"""Device wrapper classes with high-level helper methods.

These classes wrap the raw device data and provide convenient
async methods for common operations like getting location,
sending commands, etc.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .exceptions import InvalidParameterError
from .models import DeviceInfo, Location, VehicleInfo

if TYPE_CHECKING:
    from .api import LoJackClient


class Device:
    """Device wrapper providing high-level helpers for a tracked device.

    This class wraps a device and provides convenient async methods
    for interacting with it through the LoJack API.

    Attributes:
        id: The device ID.
        name: The device name (if available).
        info: The underlying DeviceInfo dataclass with full device data.
        client: Reference to the LoJackClient for API calls.
    """

    def __init__(
        self,
        client: LoJackClient,
        info: DeviceInfo,
    ) -> None:
        """Initialize the device wrapper.

        Args:
            client: The LoJackClient instance for API calls.
            info: The DeviceInfo dataclass with device data.
        """
        self._client = client
        self._info = info
        self._cached_location: Location | None = None
        self._last_refresh: datetime | None = None

    @property
    def id(self) -> str:
        """Return the device ID."""
        return self._info.id

    @property
    def name(self) -> str | None:
        """Return the device name."""
        return self._info.name

    @property
    def info(self) -> DeviceInfo:
        """Return the underlying DeviceInfo dataclass."""
        return self._info

    @property
    def last_seen(self) -> datetime | None:
        """Return when the device was last seen."""
        return self._info.last_seen

    @property
    def cached_location(self) -> Location | None:
        """Return the cached location (may be stale)."""
        return self._cached_location

    @property
    def last_refresh(self) -> datetime | None:
        """Return when the location was last refreshed."""
        return self._last_refresh

    async def refresh(self, *, force: bool = False) -> None:
        """Refresh the device's cached location.

        Fetches location from the asset's lastLocation for coordinates,
        then enriches it with telemetry data from the latest event
        (speed, battery_voltage, signal_strength, etc.).

        Args:
            force: If True, always fetch new data even if cached.
        """
        if not force and self._cached_location is not None:
            return

        # First try to get current location from asset's lastLocation
        location = await self._client.get_current_location(self.id)

        # Always fetch latest event for telemetry data
        events = await self._client.get_locations(self.id, limit=1)
        latest_event = events[0] if events else None

        if location and location.latitude is not None:
            # Enrich the lastLocation with telemetry from the event
            if latest_event:
                _enrich_location_from_event(location, latest_event)
            self._cached_location = location
        elif latest_event:
            # Use the event location directly (it has all the telemetry)
            self._cached_location = latest_event
        else:
            self._cached_location = None

        self._last_refresh = datetime.now(timezone.utc)

    async def get_location(self, *, force: bool = False) -> Location | None:
        """Get the device's current location.

        Args:
            force: If True, fetch fresh data from the API.

        Returns:
            The device's location, or None if unavailable.
        """
        if force or self._cached_location is None:
            await self.refresh(force=force)
        return self._cached_location

    async def get_history(
        self,
        *,
        limit: int = 100,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> AsyncIterator[Location]:
        """Iterate over the device's location history.

        Args:
            limit: Maximum number of locations to return (-1 for all).
            start_time: Optional start time filter.
            end_time: Optional end time filter.

        Yields:
            Location objects from newest to oldest.
        """
        locations = await self._client.get_locations(
            self.id,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )
        for loc in locations:
            yield loc

    async def send_command(self, command: str) -> bool:
        """Send a raw command to the device.

        Args:
            command: The command string to send.

        Returns:
            True if the command was accepted.

        Raises:
            CommandError: If the command fails.
        """
        return await self._client.send_command(self.id, command)

    async def request_location_update(self) -> bool:
        """Request the device to report its current location.

        Returns:
            True if the request was accepted.
        """
        return await self.send_command("locate")

    async def lock(
        self,
        *,
        message: str | None = None,
        passcode: str | None = None,
    ) -> bool:
        """Lock the device.

        Args:
            message: Optional message to display on the device.
            passcode: Optional passcode for unlocking.

        Returns:
            True if the lock command was accepted.
        """
        command = "lock"

        if message:
            # Sanitize the message
            sanitized = _sanitize_message(message)
            if sanitized:
                command = f"lock {sanitized}"

        if passcode:
            if not _is_valid_passcode(passcode):
                raise InvalidParameterError(
                    "passcode",
                    passcode,
                    "Must be alphanumeric ASCII characters only",
                )

        return await self.send_command(command)

    async def unlock(self) -> bool:
        """Unlock the device.

        Returns:
            True if the unlock command was accepted.
        """
        return await self.send_command("unlock")

    async def ring(self, *, duration: int | None = None) -> bool:
        """Make the device ring/alarm.

        Args:
            duration: Optional duration in seconds.

        Returns:
            True if the ring command was accepted.
        """
        command = "ring"
        if duration is not None:
            if duration < 1 or duration > 300:
                raise InvalidParameterError(
                    "duration",
                    duration,
                    "Must be between 1 and 300 seconds",
                )
            command = f"ring {duration}"
        return await self.send_command(command)

    def __repr__(self) -> str:
        return f"Device(id={self.id!r}, name={self.name!r})"


class Vehicle(Device):
    """Vehicle-specific device wrapper with additional vehicle data.

    Extends Device with vehicle-specific properties like VIN,
    make, model, etc.
    """

    def __init__(
        self,
        client: LoJackClient,
        info: VehicleInfo,
    ) -> None:
        """Initialize the vehicle wrapper.

        Args:
            client: The LoJackClient instance for API calls.
            info: The VehicleInfo dataclass with vehicle data.
        """
        super().__init__(client, info)
        self._vehicle_info = info

    @property
    def info(self) -> VehicleInfo:
        """Return the underlying VehicleInfo dataclass."""
        return self._vehicle_info

    @property
    def vin(self) -> str | None:
        """Return the vehicle's VIN."""
        return self._vehicle_info.vin

    @property
    def make(self) -> str | None:
        """Return the vehicle's make."""
        return self._vehicle_info.make

    @property
    def model(self) -> str | None:
        """Return the vehicle's model."""
        return self._vehicle_info.model

    @property
    def year(self) -> int | None:
        """Return the vehicle's year."""
        return self._vehicle_info.year

    @property
    def license_plate(self) -> str | None:
        """Return the vehicle's license plate."""
        return self._vehicle_info.license_plate

    @property
    def odometer(self) -> float | None:
        """Return the vehicle's odometer reading."""
        return self._vehicle_info.odometer

    async def start_engine(self) -> bool:
        """Remote start the vehicle's engine.

        Returns:
            True if the command was accepted.
        """
        return await self.send_command("start")

    async def stop_engine(self) -> bool:
        """Remote stop the vehicle's engine.

        Returns:
            True if the command was accepted.
        """
        return await self.send_command("stop")

    async def honk_horn(self) -> bool:
        """Honk the vehicle's horn.

        Returns:
            True if the command was accepted.
        """
        return await self.send_command("honk")

    async def flash_lights(self) -> bool:
        """Flash the vehicle's lights.

        Returns:
            True if the command was accepted.
        """
        return await self.send_command("flash")

    def __repr__(self) -> str:
        return f"Vehicle(id={self.id!r}, name={self.name!r}, vin={self.vin!r})"


def _sanitize_message(message: str, max_length: int = 120) -> str:
    """Sanitize a message for sending to a device.

    Removes potentially dangerous characters and limits length.
    """
    # Normalize whitespace
    sanitized = " ".join(message.strip().split())

    # Remove potentially dangerous characters
    for char in ['"', "'", "`", ";", "\\", "\n", "\r"]:
        sanitized = sanitized.replace(char, "")

    # Limit length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]

    return sanitized


def _is_valid_passcode(passcode: str) -> bool:
    """Validate a passcode contains only safe characters."""
    return all(c.isalnum() and ord(c) < 128 for c in passcode)


def _enrich_location_from_event(location: Location, event: Location) -> None:
    """Enrich a location with telemetry data from an event.

    The asset's lastLocation typically only has coordinates, while
    events contain rich telemetry data. This merges them.

    Args:
        location: The location to enrich (modified in place).
        event: The event location with telemetry data.
    """
    # Only copy telemetry if the location is missing it
    if location.speed is None and event.speed is not None:
        location.speed = event.speed

    if location.heading is None and event.heading is not None:
        location.heading = event.heading

    if location.odometer is None and event.odometer is not None:
        location.odometer = event.odometer

    if location.battery_voltage is None and event.battery_voltage is not None:
        location.battery_voltage = event.battery_voltage

    if location.engine_hours is None and event.engine_hours is not None:
        location.engine_hours = event.engine_hours

    if location.distance_driven is None and event.distance_driven is not None:
        location.distance_driven = event.distance_driven

    if location.signal_strength is None and event.signal_strength is not None:
        location.signal_strength = event.signal_strength

    if location.gps_fix_quality is None and event.gps_fix_quality is not None:
        location.gps_fix_quality = event.gps_fix_quality

    if location.event_type is None and event.event_type is not None:
        location.event_type = event.event_type

    if location.event_id is None and event.event_id is not None:
        location.event_id = event.event_id

    if location.address is None and event.address is not None:
        location.address = event.address

    # Also update timestamp if the event has a more recent one
    if event.timestamp is not None:
        if location.timestamp is None or event.timestamp > location.timestamp:
            location.timestamp = event.timestamp
