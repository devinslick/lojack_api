"""High-level Spireon LoJack API client.

This module provides the main entry point for interacting with the
Spireon LoJack API. It follows Home Assistant best practices for async
integrations.
"""

from __future__ import annotations

import ssl
from datetime import datetime
from typing import Any

import aiohttp

from .auth import DEFAULT_APP_TOKEN, AuthArtifacts, AuthManager
from .device import Device, Vehicle
from .exceptions import ApiError, DeviceNotFoundError
from .models import (
    DeviceInfo,
    Geofence,
    Location,
    MaintenanceSchedule,
    RepairOrder,
    VehicleInfo,
    _parse_timestamp,
)
from .transport import AiohttpTransport

# Default Spireon API endpoints
IDENTITY_URL = "https://identity.spireon.com"
SERVICES_URL = "https://services.spireon.com/v0/rest"


class LoJackClient:
    """High-level async client for the Spireon LoJack API.

    This client provides a clean interface for interacting with LoJack
    devices. It supports both context manager usage and manual lifecycle
    management.

    The Spireon LoJack API uses separate services:
    - Identity service for authentication
    - Services API for device/asset management

    Example usage with context manager (recommended):
        async with await LoJackClient.create(username, password) as client:
            devices = await client.list_devices()
            for device in devices:
                location = await device.get_location()

    Example usage with manual lifecycle:
        client = await LoJackClient.create(username, password)
        try:
            devices = await client.list_devices()
        finally:
            await client.close()

    Example usage with session resumption:
        # First time - login and save auth
        client = await LoJackClient.create(username, password)
        auth_data = client.export_auth().to_dict()
        save_to_storage(auth_data)
        await client.close()

        # Later - resume without password
        auth = AuthArtifacts.from_dict(load_from_storage())
        client = await LoJackClient.from_auth(auth)
    """

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        identity_url: str = IDENTITY_URL,
        services_url: str = SERVICES_URL,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
        app_token: str = DEFAULT_APP_TOKEN,
    ) -> None:
        """Initialize the client.

        Note: Use the `create()` classmethod for proper async initialization.

        Args:
            username: LoJack account username/email.
            password: LoJack account password.
            identity_url: URL for the identity service (auth).
            services_url: URL for the services API.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.
            app_token: The X-Nspire-Apptoken value.
        """
        self._identity_url = identity_url.rstrip("/")
        self._services_url = services_url.rstrip("/")

        # Separate transports for identity and services
        self._identity_transport = AiohttpTransport(
            identity_url,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
        )
        self._services_transport = AiohttpTransport(
            services_url,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
        )

        self._auth = AuthManager(
            self._identity_transport,
            username,
            password,
            app_token=app_token,
        )
        self._closed = False

    @classmethod
    async def create(
        cls,
        username: str,
        password: str,
        identity_url: str = IDENTITY_URL,
        services_url: str = SERVICES_URL,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
        app_token: str = DEFAULT_APP_TOKEN,
    ) -> LoJackClient:
        """Create a new client and authenticate.

        This is the recommended way to create a client instance.

        Args:
            username: LoJack account username/email.
            password: LoJack account password.
            identity_url: URL for the identity service.
            services_url: URL for the services API.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.
            app_token: The X-Nspire-Apptoken value.

        Returns:
            An authenticated LoJackClient instance.

        Raises:
            AuthenticationError: If login fails.
        """
        client = cls(
            username=username,
            password=password,
            identity_url=identity_url,
            services_url=services_url,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
            app_token=app_token,
        )
        await client._auth.login()
        return client

    @classmethod
    async def from_auth(
        cls,
        auth_artifacts: AuthArtifacts,
        identity_url: str = IDENTITY_URL,
        services_url: str = SERVICES_URL,
        session: aiohttp.ClientSession | None = None,
        timeout: float = 30.0,
        ssl_context: ssl.SSLContext | None = None,
        app_token: str = DEFAULT_APP_TOKEN,
        username: str | None = None,
        password: str | None = None,
    ) -> LoJackClient:
        """Create a client from previously exported auth artifacts.

        This allows session resumption without re-entering credentials.
        The token will be refreshed if expired (requires username/password).

        Args:
            auth_artifacts: Previously exported authentication state.
            identity_url: URL for the identity service.
            services_url: URL for the services API.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.
            app_token: The X-Nspire-Apptoken value.
            username: Optional username for token refresh fallback.
            password: Optional password for token refresh fallback.

        Returns:
            A LoJackClient instance with restored authentication.
        """
        client = cls(
            username=username,
            password=password,
            identity_url=identity_url,
            services_url=services_url,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
            app_token=app_token,
        )
        client._auth.import_auth_artifacts(auth_artifacts)
        return client

    async def __aenter__(self) -> LoJackClient:
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context manager and clean up resources."""
        await self.close()

    @property
    def is_authenticated(self) -> bool:
        """Return True if the client has valid authentication."""
        return self._auth.is_authenticated

    @property
    def user_id(self) -> str | None:
        """Return the authenticated user ID if available."""
        return self._auth.user_id

    def export_auth(self) -> AuthArtifacts | None:
        """Export current authentication state for later resumption.

        Returns:
            AuthArtifacts if authenticated, None otherwise.
        """
        return self._auth.export_auth_artifacts()

    async def _get_headers(self) -> dict[str, str]:
        """Get headers for authenticated service requests."""
        # Ensure we have a valid token
        await self._auth.get_token()
        return self._auth.get_auth_headers()

    async def list_devices(self) -> list[Device | Vehicle]:
        """List all assets (devices/vehicles) associated with the account.

        Returns:
            A list of Device or Vehicle objects.
        """
        headers = await self._get_headers()
        data = await self._services_transport.request("GET", "/assets", headers=headers)

        devices: list[Device | Vehicle] = []

        # Handle Spireon response format: { "content": [...] }
        items: list[Any] = []
        if isinstance(data, dict):
            items = (
                data.get("content")
                or data.get("devices")
                or data.get("assets")
                or data.get("vehicles")
                or []
            )
        elif isinstance(data, list):
            items = data

        for item in items:
            if not isinstance(item, dict):
                continue

            # Determine if this is a vehicle or generic device
            # Spireon assets typically have "attributes" with vehicle info
            attrs = item.get("attributes", {})
            if attrs.get("vin") or item.get("vin"):
                vehicle_info = VehicleInfo.from_api(item)
                devices.append(Vehicle(self, vehicle_info))
            else:
                device_info = DeviceInfo.from_api(item)
                devices.append(Device(self, device_info))

        return devices

    async def get_device(self, device_id: str) -> Device | Vehicle:
        """Get a specific asset by ID.

        Args:
            device_id: The asset ID to fetch.

        Returns:
            A Device or Vehicle object.

        Raises:
            DeviceNotFoundError: If the asset is not found.
        """
        headers = await self._get_headers()
        path = f"/assets/{device_id}"

        try:
            data = await self._services_transport.request("GET", path, headers=headers)
        except ApiError as e:
            if e.status_code == 404:
                raise DeviceNotFoundError(device_id) from e
            raise

        if not isinstance(data, dict):
            raise DeviceNotFoundError(device_id)

        # Check for nested data
        item: dict[str, Any] = data.get("content") or data.get("asset") or data

        attrs = item.get("attributes", {})
        if attrs.get("vin") or item.get("vin"):
            vehicle_info = VehicleInfo.from_api(item)
            return Vehicle(self, vehicle_info)
        else:
            device_info = DeviceInfo.from_api(item)
            return Device(self, device_info)

    async def get_locations(
        self,
        device_id: str,
        *,
        limit: int = -1,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        skip_empty: bool = False,
    ) -> list[Location]:
        """Get location history (events) for a device.

        Args:
            device_id: The asset ID.
            limit: Maximum number of locations to return (-1 for all).
            start_time: Optional start time filter.
            end_time: Optional end time filter.
            skip_empty: If True, skip empty location entries.

        Returns:
            A list of Location objects.
        """
        headers = await self._get_headers()
        params: dict[str, Any] = {}

        if limit != -1:
            params["limit"] = limit
        if start_time:
            # Spireon uses this format: 2022-05-10T03:59:59.999+0000
            params["startDate"] = start_time.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
        if end_time:
            params["endDate"] = end_time.strftime("%Y-%m-%dT%H:%M:%S.000+0000")

        # Spireon uses /assets/{id}/events endpoint for location history
        path = f"/assets/{device_id}/events"
        data = await self._services_transport.request(
            "GET", path, params=params, headers=headers
        )

        # Parse response
        raw_events: list[Any] = []
        if isinstance(data, dict):
            raw_events = (
                data.get("content")
                or data.get("events")
                or data.get("locations")
                or data.get("history")
                or []
            )
        elif isinstance(data, list):
            raw_events = data

        locations: list[Location] = []
        for item in raw_events:
            if isinstance(item, dict):
                loc = Location.from_event(item)

                # Skip empty if requested
                if skip_empty and loc.latitude is None and loc.longitude is None:
                    continue

                locations.append(loc)

        return locations

    async def get_current_location(self, device_id: str) -> Location | None:
        """Get the current location for a device from the asset data.

        This returns the lastLocation from the asset, which is more
        current than fetching from events.

        Args:
            device_id: The asset ID.

        Returns:
            The current Location, or None if unavailable.
        """
        headers = await self._get_headers()
        path = f"/assets/{device_id}"

        try:
            data = await self._services_transport.request("GET", path, headers=headers)
        except ApiError:
            return None

        if not isinstance(data, dict):
            return None

        # Get lastLocation from asset
        last_location = data.get("lastLocation")
        if not last_location:
            return None

        loc = Location.from_api(last_location)

        # Add timestamp from locationLastReported
        if not loc.timestamp:
            ts = data.get("locationLastReported")
            if ts:
                loc.timestamp = _parse_timestamp(ts)

        # Add speed from asset
        if loc.speed is None:
            speed = data.get("speed")
            if speed is not None:
                try:
                    loc.speed = float(speed)
                except (ValueError, TypeError):
                    pass

        return loc

    async def send_command(self, device_id: str, command: str) -> bool:
        """Send a command to a device.

        Args:
            device_id: The asset ID.
            command: The command type to send.

        Returns:
            True if the command was accepted.
        """
        headers = await self._get_headers()

        # Spireon uses specific command format
        payload = {
            "command": command.upper(),
            "responseStrategy": "ASYNC",
        }

        path = f"/assets/{device_id}/commands"
        data = await self._services_transport.request(
            "POST", path, json=payload, headers=headers
        )

        if isinstance(data, dict):
            # Check for successful command submission
            return bool(
                data.get("id")
                or data.get("commandId")
                or data.get("ok")
                or data.get("accepted")
                or data.get("success")
                or data.get("status") in ("ok", "PENDING", "SUBMITTED")
            )
        return True

    async def update_asset(
        self,
        device_id: str,
        *,
        name: str | None = None,
        color: str | None = None,
        make: str | None = None,
        model: str | None = None,
        year: int | None = None,
        vin: str | None = None,
        odometer: float | None = None,
    ) -> bool:
        """Update asset information.

        Args:
            device_id: The asset ID to update.
            name: New name for the asset.
            color: Vehicle color.
            make: Vehicle make.
            model: Vehicle model.
            year: Vehicle year.
            vin: Vehicle VIN.
            odometer: Current odometer reading.

        Returns:
            True if the update was successful.
        """
        headers = await self._get_headers()

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if color is not None:
            payload["color"] = color
        if make is not None:
            payload["make"] = make
        if model is not None:
            payload["model"] = model
        if year is not None:
            payload["year"] = year
        if vin is not None:
            payload["vin"] = vin
        if odometer is not None:
            payload["odometer"] = odometer

        if not payload:
            return True  # Nothing to update

        path = f"/assets/{device_id}"
        await self._services_transport.request(
            "PUT", path, json=payload, headers=headers
        )
        return True

    async def list_geofences(
        self,
        device_id: str,
        *,
        limit: int = -1,
        offset: int = 0,
    ) -> list[Geofence]:
        """List geofences for a device.

        Args:
            device_id: The asset ID.
            limit: Maximum number of geofences to return (-1 for all).
            offset: Number of geofences to skip.

        Returns:
            A list of Geofence objects.
        """
        headers = await self._get_headers()
        params: dict[str, Any] = {}

        if limit != -1:
            params["limit"] = limit
        if offset > 0:
            params["offset"] = offset

        path = f"/assets/{device_id}/geofences"
        data = await self._services_transport.request(
            "GET", path, params=params, headers=headers
        )

        geofences: list[Geofence] = []
        raw_items: list[Any] = []

        if isinstance(data, dict):
            raw_items = (
                data.get("content")
                or data.get("geofences")
                or data.get("items")
                or []
            )
        elif isinstance(data, list):
            raw_items = data

        for item in raw_items:
            if isinstance(item, dict):
                geofences.append(Geofence.from_api(item, asset_id=device_id))

        return geofences

    async def get_geofence(self, device_id: str, geofence_id: str) -> Geofence | None:
        """Get a specific geofence.

        Args:
            device_id: The asset ID.
            geofence_id: The geofence ID.

        Returns:
            The Geofence, or None if not found.
        """
        headers = await self._get_headers()
        path = f"/assets/{device_id}/geofences/{geofence_id}"

        try:
            data = await self._services_transport.request("GET", path, headers=headers)
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

        if not isinstance(data, dict):
            return None

        return Geofence.from_api(data, asset_id=device_id)

    async def create_geofence(
        self,
        device_id: str,
        *,
        name: str,
        latitude: float,
        longitude: float,
        radius: float = 100.0,
        address: str | None = None,
    ) -> Geofence | None:
        """Create a new geofence for a device.

        Args:
            device_id: The asset ID.
            name: Display name for the geofence.
            latitude: Center point latitude.
            longitude: Center point longitude.
            radius: Radius in meters (default: 100).
            address: Optional address description.

        Returns:
            The created Geofence, or None if creation failed.
        """
        headers = await self._get_headers()

        payload: dict[str, Any] = {
            "name": name,
            "location": {
                "coordinates": {
                    "lat": latitude,
                    "lng": longitude,
                },
                "radius": radius,
            },
            "active": True,
        }

        if address:
            payload["location"]["address"] = {"line1": address}

        path = f"/assets/{device_id}/geofences"
        data = await self._services_transport.request(
            "POST", path, json=payload, headers=headers
        )

        if isinstance(data, dict):
            return Geofence.from_api(data, asset_id=device_id)
        return None

    async def update_geofence(
        self,
        device_id: str,
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
            device_id: The asset ID.
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
        headers = await self._get_headers()

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if active is not None:
            payload["active"] = active

        # Build location update if any location fields provided
        if latitude is not None or longitude is not None or radius is not None:
            location: dict[str, Any] = {}
            if latitude is not None or longitude is not None:
                location["coordinates"] = {}
                if latitude is not None:
                    location["coordinates"]["lat"] = latitude
                if longitude is not None:
                    location["coordinates"]["lng"] = longitude
            if radius is not None:
                location["radius"] = radius
            if address is not None:
                location["address"] = {"line1": address}
            payload["location"] = location

        if not payload:
            return True  # Nothing to update

        path = f"/assets/{device_id}/geofences/{geofence_id}"
        await self._services_transport.request(
            "PUT", path, json=payload, headers=headers
        )
        return True

    async def delete_geofence(self, device_id: str, geofence_id: str) -> bool:
        """Delete a geofence.

        Args:
            device_id: The asset ID.
            geofence_id: The geofence ID to delete.

        Returns:
            True if the deletion was successful.
        """
        headers = await self._get_headers()
        path = f"/assets/{device_id}/geofences/{geofence_id}"

        await self._services_transport.request("DELETE", path, headers=headers)
        return True

    async def get_maintenance_schedule(self, vin: str) -> MaintenanceSchedule | None:
        """Get maintenance schedule for a vehicle by VIN.

        Args:
            vin: Vehicle identification number.

        Returns:
            MaintenanceSchedule with service items, or None if not found.
        """
        headers = await self._get_headers()
        params = {"vin": vin}

        # Maintenance endpoint is on the services API
        path = "/automotive/maintenanceSchedule"
        try:
            data = await self._services_transport.request(
                "GET", path, params=params, headers=headers
            )
        except ApiError as e:
            if e.status_code == 404:
                return None
            raise

        if not isinstance(data, dict):
            return None

        return MaintenanceSchedule.from_api(data, vin=vin)

    async def get_repair_orders(
        self,
        *,
        vin: str | None = None,
        asset_id: str | None = None,
        sort: str = "openDate:desc",
    ) -> list[RepairOrder]:
        """Get repair orders for a vehicle.

        Either vin or asset_id must be provided.

        Args:
            vin: Vehicle identification number.
            asset_id: Asset ID.
            sort: Sort order (default: "openDate:desc").

        Returns:
            A list of RepairOrder objects.
        """
        if not vin and not asset_id:
            return []

        headers = await self._get_headers()
        params: dict[str, Any] = {"sort": sort}

        if vin:
            params["vin"] = vin
        if asset_id:
            params["assetId"] = asset_id

        path = "/repairOrders"
        try:
            data = await self._services_transport.request(
                "GET", path, params=params, headers=headers
            )
        except ApiError as e:
            if e.status_code == 404:
                return []
            raise

        orders: list[RepairOrder] = []
        raw_items: list[Any] = []

        if isinstance(data, dict):
            raw_items = (
                data.get("content")
                or data.get("repairOrders")
                or data.get("orders")
                or []
            )
        elif isinstance(data, list):
            raw_items = data

        for item in raw_items:
            if isinstance(item, dict):
                orders.append(RepairOrder.from_api(item))

        return orders

    async def get_user_info(self) -> dict[str, Any] | None:
        """Get information about the authenticated user.

        Returns:
            User profile information as a dictionary, or None if unavailable.
        """
        headers = await self._get_headers()
        path = "/identity"

        try:
            data = await self._services_transport.request("GET", path, headers=headers)
        except ApiError:
            return None

        if isinstance(data, dict):
            return data
        return None

    async def get_accounts(self) -> list[dict[str, Any]]:
        """Get all accounts associated with the user.

        Returns:
            A list of account dictionaries.
        """
        headers = await self._get_headers()
        path = "/accounts"

        try:
            data = await self._services_transport.request("GET", path, headers=headers)
        except ApiError:
            return []

        if isinstance(data, dict):
            return data.get("content") or data.get("accounts") or []
        elif isinstance(data, list):
            return data
        return []

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._closed:
            return

        self._closed = True
        await self._identity_transport.close()
        await self._services_transport.close()
