from typing import Any, Dict, List, Optional
import base64

from .transport import AiohttpClient
from .auth import AuthManager
from .devices import Device, Vehicle


class LoJackClient:
    """High-level LoJack API client.

    Provides a small set of convenience methods the `Device` wrapper expects:
    - `get_locations` -> list of JSON location mappings
    - `send_command` -> command helper

    Note: this is intentionally minimal; integrations can call `transport`
    directly for other endpoints.
    """

    def __init__(self, base_url: str, username: str, password: str, session: Optional[object] = None):
        self.base_url = base_url
        self.transport = AiohttpClient(base_url, session=session)
        self.auth = AuthManager(self.transport, username, password)

    @classmethod
    async def create(cls, base_url: str, username: str, password: str, session: Optional[object] = None) -> "LoJackClient":
        client = cls(base_url, username, password, session=session)
        # perform initial login to obtain token (no password persistence semantics here)
        await client.auth.login()
        return client

    async def close(self) -> None:
        await self.transport.close()

    async def _auth_headers(self) -> Optional[Dict[str, str]]:
        token = await self.auth.get_token()
        return {"Authorization": f"Bearer {token}"} if token else None

    async def list_devices(self) -> List[Device]:
        headers = await self._auth_headers()
        data = await self.transport.request("GET", "/devices", headers=headers)
        devices: List[Device] = []
        for item in (data.get("devices") if isinstance(data, dict) else []):
            dev = Vehicle(id=item.get("id"), name=item.get("name"))
            dev.update_from_api(item)
            devices.append(dev)
        return devices

    async def get_locations(self, device_id: str, num_to_get: int = -1, *, skip_empty: bool = False) -> List[str]:
        """Return a list of encrypted location blobs (usually base64 strings).

        `num_to_get=-1` means request all available; the transport maps this to
        a backend query param if supported.
        """
        headers = await self._auth_headers()
        params: Dict[str, Any] = {}
        if num_to_get != -1:
            params["limit"] = num_to_get
        if skip_empty:
            params["skip_empty"] = "1"
        path = f"/devices/{device_id}/locations"
        data = await self.transport.request("GET", path, params=params, headers=headers)
        # Expect server to return {"locations": [...] } or a raw list
        if isinstance(data, dict) and "locations" in data:
            return data.get("locations") or []
        if isinstance(data, list):
            return data
        return []

    # Note: LoJack backend does not provide pictures or encrypted blobs.
    # The client exposes only location retrieval and command sending.

    async def send_command(self, device_id: str, command: str) -> bool:
        headers = await self._auth_headers()
        payload = {"command": command}
        path = f"/devices/{device_id}/commands"
        data = await self.transport.request("POST", path, json=payload, headers=headers)
        if isinstance(data, dict):
            return bool(data.get("ok") or data.get("accepted") or data.get("success"))
        return True
