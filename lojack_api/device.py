"""Device wrapper classes with high-level helper methods.

These classes wrap the raw device data and provide convenient
async methods for common operations like getting location,
sending commands, etc.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

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

    async def request_fresh_location(self) -> datetime | None:
        """Request a fresh location update from the device (non-blocking).

        Sends a "locate" command and returns the current location timestamp
        for later comparison. Use this with subsequent `get_location(force=True)`
        calls to detect when fresh data arrives.

        This is the recommended approach for Home Assistant integrations:
        1. Call `request_fresh_location()` to send the locate command
        2. On subsequent coordinator updates, call `get_location(force=True)`
        3. Compare timestamps to detect fresh data

        Returns:
            The current location timestamp (before the locate command),
            or None if no location is available. Use this to detect when
            fresh data arrives in subsequent polls.

        Example (Home Assistant pattern):
            # In a service call or button press handler:
            baseline_ts = await device.request_fresh_location()

            # In your coordinator's _async_update_data:
            location = await device.get_location(force=True)
            if location and baseline_ts and location.timestamp > baseline_ts:
                # Fresh data has arrived
                pass
        """
        # Get current timestamp for comparison
        current_location = await self._client.get_current_location(self.id)
        baseline_timestamp = current_location.timestamp if current_location else None

        # Send locate command (fire and forget)
        try:
            await self.send_command("locate")
        except Exception:
            # Command may fail, but we still return the baseline
            pass

        return baseline_timestamp

    @property
    def location_timestamp(self) -> datetime | None:
        """Return the timestamp of the cached location, if available."""
        if self._cached_location:
            return self._cached_location.timestamp
        return None

    async def update(
        self,
        *,
        name: str | None = None,
        color: str | None = None,
    ) -> bool:
        """Update device information.

        Args:
            name: New name for the device.
            color: Device color.

        Returns:
            True if the update was successful.
        """
        return await self._client.update_asset(
            self.id,
            name=name,
            color=color,
        )

    async def list_geofences(self) -> list:
        """List all geofences for this device.

        Returns:
            A list of Geofence objects.
        """
        return await self._client.list_geofences(self.id)

    async def get_geofence(self, geofence_id: str):
        """Get a specific geofence.

        Args:
            geofence_id: The geofence ID.

        Returns:
            The Geofence, or None if not found.
        """
        return await self._client.get_geofence(self.id, geofence_id)

    async def create_geofence(
        self,
        *,
        name: str,
        latitude: float,
        longitude: float,
        radius: float = 100.0,
        address: str | None = None,
    ):
        """Create a new geofence for this device.

        Args:
            name: Display name for the geofence.
            latitude: Center point latitude.
            longitude: Center point longitude.
            radius: Radius in meters (default: 100).
            address: Optional address description.

        Returns:
            The created Geofence, or None if creation failed.
        """
        return await self._client.create_geofence(
            self.id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            address=address,
        )

    async def update_geofence(
        self,
        geofence_id: str,
        *,
        name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius: float | None = None,
        address: str | None = None,
        active: bool | None = None,
    ) -> bool:
        """Update an existing geofence.

        Args:
            geofence_id: The geofence ID to update.
            name: New display name.
            latitude: New center point latitude.
            longitude: New center point longitude.
            radius: New radius in meters.
            address: New address description.
            active: Whether the geofence is active.

        Returns:
            True if the update was successful.
        """
        return await self._client.update_geofence(
            self.id,
            geofence_id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius=radius,
            address=address,
            active=active,
        )

    async def delete_geofence(self, geofence_id: str) -> bool:
        """Delete a geofence.

        Args:
            geofence_id: The geofence ID to delete.

        Returns:
            True if the deletion was successful.
        """
        return await self._client.delete_geofence(self.id, geofence_id)

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

    async def update(
        self,
        *,
        name: str | None = None,
        color: str | None = None,
        make: str | None = None,
        model: str | None = None,
        year: int | None = None,
        vin: str | None = None,
        odometer: float | None = None,
    ) -> bool:
        """Update vehicle information.

        Args:
            name: New name for the vehicle.
            color: Vehicle color.
            make: Vehicle make.
            model: Vehicle model.
            year: Vehicle year.
            vin: Vehicle VIN.
            odometer: Current odometer reading.

        Returns:
            True if the update was successful.
        """
        return await self._client.update_asset(
            self.id,
            name=name,
            color=color,
            make=make,
            model=model,
            year=year,
            vin=vin,
            odometer=odometer,
        )

    async def get_maintenance_schedule(self):
        """Get the maintenance schedule for this vehicle.

        Requires the vehicle to have a VIN.

        Returns:
            MaintenanceSchedule with service items, or None if unavailable.
        """
        if not self.vin:
            return None
        return await self._client.get_maintenance_schedule(self.vin)

    async def get_repair_orders(self):
        """Get repair orders for this vehicle.

        Returns:
            A list of RepairOrder objects.
        """
        return await self._client.get_repair_orders(
            vin=self.vin,
            asset_id=self.id,
        )

    def __repr__(self) -> str:
        return f"Vehicle(id={self.id!r}, name={self.name!r}, vin={self.vin!r})"


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
