"""Device wrapper classes with high-level helper methods.

These classes wrap the raw device data and provide convenient
async methods for common operations like getting location,
sending commands, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Optional

from .exceptions import CommandError, InvalidParameterError
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
        client: "LoJackClient",
        info: DeviceInfo,
    ) -> None:
        """Initialize the device wrapper.

        Args:
            client: The LoJackClient instance for API calls.
            info: The DeviceInfo dataclass with device data.
        """
        self._client = client
        self._info = info
        self._cached_location: Optional[Location] = None
        self._last_refresh: Optional[datetime] = None

    @property
    def id(self) -> str:
        """Return the device ID."""
        return self._info.id

    @property
    def name(self) -> Optional[str]:
        """Return the device name."""
        return self._info.name

    @property
    def info(self) -> DeviceInfo:
        """Return the underlying DeviceInfo dataclass."""
        return self._info

    @property
    def last_seen(self) -> Optional[datetime]:
        """Return when the device was last seen."""
        return self._info.last_seen

    @property
    def cached_location(self) -> Optional[Location]:
        """Return the cached location (may be stale)."""
        return self._cached_location

    @property
    def last_refresh(self) -> Optional[datetime]:
        """Return when the location was last refreshed."""
        return self._last_refresh

    async def refresh(self, *, force: bool = False) -> None:
        """Refresh the device's cached location.

        Args:
            force: If True, always fetch new data even if cached.
        """
        if not force and self._cached_location is not None:
            return

        locations = await self._client.get_locations(self.id, limit=1)
        if locations:
            self._cached_location = locations[0]
        else:
            self._cached_location = None

        self._last_refresh = datetime.now(timezone.utc)

    async def get_location(self, *, force: bool = False) -> Optional[Location]:
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
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
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
        message: Optional[str] = None,
        passcode: Optional[str] = None,
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

    async def ring(self, *, duration: Optional[int] = None) -> bool:
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
        client: "LoJackClient",
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
    def vin(self) -> Optional[str]:
        """Return the vehicle's VIN."""
        return self._vehicle_info.vin

    @property
    def make(self) -> Optional[str]:
        """Return the vehicle's make."""
        return self._vehicle_info.make

    @property
    def model(self) -> Optional[str]:
        """Return the vehicle's model."""
        return self._vehicle_info.model

    @property
    def year(self) -> Optional[int]:
        """Return the vehicle's year."""
        return self._vehicle_info.year

    @property
    def license_plate(self) -> Optional[str]:
        """Return the vehicle's license plate."""
        return self._vehicle_info.license_plate

    @property
    def odometer(self) -> Optional[float]:
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
