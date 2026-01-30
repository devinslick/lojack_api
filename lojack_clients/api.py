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
from .models import DeviceInfo, Location, VehicleInfo
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
                from .models import _parse_timestamp
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

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._closed:
            return

        self._closed = True
        await self._identity_transport.close()
        await self._services_transport.close()
