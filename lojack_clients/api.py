"""High-level LoJack API client.

This module provides the main entry point for interacting with the
LoJack API. It follows Home Assistant best practices for async
integrations.
"""

from __future__ import annotations

import ssl
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import aiohttp

from .auth import AuthArtifacts, AuthManager
from .device import Device, Vehicle
from .exceptions import ApiError, AuthenticationError, DeviceNotFoundError
from .models import DeviceInfo, Location, VehicleInfo
from .transport import AiohttpTransport


class LoJackClient:
    """High-level async client for the LoJack API.

    This client provides a clean interface for interacting with LoJack
    devices. It supports both context manager usage and manual lifecycle
    management.

    Example usage with context manager (recommended):
        async with await LoJackClient.create(url, username, password) as client:
            devices = await client.list_devices()
            for device in devices:
                location = await device.get_location()

    Example usage with manual lifecycle:
        client = await LoJackClient.create(url, username, password)
        try:
            devices = await client.list_devices()
        finally:
            await client.close()

    Example usage with session resumption:
        # First time - login and save auth
        client = await LoJackClient.create(url, username, password)
        auth_data = client.export_auth().to_dict()
        save_to_storage(auth_data)
        await client.close()

        # Later - resume without password
        auth = AuthArtifacts.from_dict(load_from_storage())
        client = await LoJackClient.from_auth(url, auth)
    """

    def __init__(
        self,
        base_url: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: float = 30.0,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> None:
        """Initialize the client.

        Note: Use the `create()` classmethod for proper async initialization.

        Args:
            base_url: The base URL of the LoJack API.
            username: LoJack account username/email.
            password: LoJack account password.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.
        """
        self._base_url = base_url.rstrip("/")
        self._transport = AiohttpTransport(
            base_url,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
        )
        self._auth = AuthManager(self._transport, username, password)
        self._closed = False

    @classmethod
    async def create(
        cls,
        base_url: str,
        username: str,
        password: str,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: float = 30.0,
        ssl_context: Optional[ssl.SSLContext] = None,
    ) -> "LoJackClient":
        """Create a new client and authenticate.

        This is the recommended way to create a client instance.

        Args:
            base_url: The base URL of the LoJack API.
            username: LoJack account username/email.
            password: LoJack account password.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.

        Returns:
            An authenticated LoJackClient instance.

        Raises:
            AuthenticationError: If login fails.
        """
        client = cls(
            base_url,
            username=username,
            password=password,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
        )
        await client._auth.login()
        return client

    @classmethod
    async def from_auth(
        cls,
        base_url: str,
        auth_artifacts: AuthArtifacts,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: float = 30.0,
        ssl_context: Optional[ssl.SSLContext] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> "LoJackClient":
        """Create a client from previously exported auth artifacts.

        This allows session resumption without re-entering credentials.
        The token will be refreshed if expired.

        Args:
            base_url: The base URL of the LoJack API.
            auth_artifacts: Previously exported authentication state.
            session: Optional existing aiohttp session to use.
            timeout: Request timeout in seconds.
            ssl_context: Optional SSL context for custom certificates.
            username: Optional username for token refresh fallback.
            password: Optional password for token refresh fallback.

        Returns:
            A LoJackClient instance with restored authentication.
        """
        client = cls(
            base_url,
            username=username,
            password=password,
            session=session,
            timeout=timeout,
            ssl_context=ssl_context,
        )
        client._auth.import_auth_artifacts(auth_artifacts)
        return client

    async def __aenter__(self) -> "LoJackClient":
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
    def user_id(self) -> Optional[str]:
        """Return the authenticated user ID if available."""
        return self._auth.user_id

    def export_auth(self) -> Optional[AuthArtifacts]:
        """Export current authentication state for later resumption.

        Returns:
            AuthArtifacts if authenticated, None otherwise.
        """
        return self._auth.export_auth_artifacts()

    async def _auth_headers(self) -> Dict[str, str]:
        """Get authorization headers with a valid token."""
        token = await self._auth.get_token()
        return {"Authorization": f"Bearer {token}"}

    async def list_devices(self) -> List[Union[Device, Vehicle]]:
        """List all devices associated with the account.

        Returns:
            A list of Device or Vehicle objects.
        """
        headers = await self._auth_headers()
        data = await self._transport.request("GET", "/devices", headers=headers)

        devices: List[Union[Device, Vehicle]] = []

        # Handle various response formats
        items: List[Any] = []
        if isinstance(data, dict):
            items = data.get("devices") or data.get("assets") or data.get("vehicles") or []
        elif isinstance(data, list):
            items = data

        for item in items:
            if not isinstance(item, dict):
                continue

            # Determine if this is a vehicle or generic device
            if item.get("vin") or item.get("type") == "vehicle":
                vehicle_info = VehicleInfo.from_api(item)
                devices.append(Vehicle(self, vehicle_info))
            else:
                device_info = DeviceInfo.from_api(item)
                devices.append(Device(self, device_info))

        return devices

    async def get_device(self, device_id: str) -> Union[Device, Vehicle]:
        """Get a specific device by ID.

        Args:
            device_id: The device ID to fetch.

        Returns:
            A Device or Vehicle object.

        Raises:
            DeviceNotFoundError: If the device is not found.
        """
        headers = await self._auth_headers()
        path = f"/devices/{device_id}"

        try:
            data = await self._transport.request("GET", path, headers=headers)
        except ApiError as e:
            if e.status_code == 404:
                raise DeviceNotFoundError(device_id) from e
            raise

        if not isinstance(data, dict):
            raise DeviceNotFoundError(device_id)

        # Check for nested device data
        item: Dict[str, Any] = data.get("device") or data.get("asset") or data

        if item.get("vin") or item.get("type") == "vehicle":
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
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip_empty: bool = False,
    ) -> List[Location]:
        """Get location history for a device.

        Args:
            device_id: The device ID.
            limit: Maximum number of locations to return (-1 for all).
            start_time: Optional start time filter.
            end_time: Optional end time filter.
            skip_empty: If True, skip empty location entries.

        Returns:
            A list of Location objects.
        """
        headers = await self._auth_headers()
        params: Dict[str, Any] = {}

        if limit != -1:
            params["limit"] = limit
        if start_time:
            params["start"] = start_time.isoformat()
        if end_time:
            params["end"] = end_time.isoformat()
        if skip_empty:
            params["skip_empty"] = "1"

        path = f"/devices/{device_id}/locations"
        data = await self._transport.request("GET", path, params=params, headers=headers)

        # Parse response
        raw_locations: List[Any] = []
        if isinstance(data, dict):
            raw_locations = data.get("locations") or data.get("history") or []
        elif isinstance(data, list):
            raw_locations = data

        locations: List[Location] = []
        for item in raw_locations:
            if isinstance(item, dict):
                locations.append(Location.from_api(item))

        return locations

    async def send_command(self, device_id: str, command: str) -> bool:
        """Send a command to a device.

        Args:
            device_id: The device ID.
            command: The command string to send.

        Returns:
            True if the command was accepted.
        """
        headers = await self._auth_headers()
        payload = {"command": command}
        path = f"/devices/{device_id}/commands"

        data = await self._transport.request("POST", path, json=payload, headers=headers)

        if isinstance(data, dict):
            return bool(
                data.get("ok")
                or data.get("accepted")
                or data.get("success")
                or data.get("status") == "ok"
            )
        return True

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._closed:
            return

        self._closed = True
        await self._transport.close()
