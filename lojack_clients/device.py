from __future__ import annotations

import json
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional


class Device:
    """Device wrapper providing high-level helpers for a single tracked device.

    Minimal methods: refresh/get_location/get_history, `lock`, and `wipe`.
    It assumes server returns JSON locations directly (no encrypted blobs).
    """
    def __init__(self, client: Any, device_id: str, raw: Optional[Dict[str, Any]] = None) -> None:
        self.client = client
        self.id = device_id
        self.raw: Dict[str, Any] = raw or {}
        self.name: Optional[str] = self.raw.get("name")
        self.cached_location: Optional[Dict[str, Any]] = None
        self._last_refresh: Optional[datetime] = None

    async def refresh(self, *, force: bool = False) -> None:
        """Refresh the device's most recent location and cache it.

        Delegates to `client.get_locations(device_id=..., num_to_get=1)` and
        expects the server to return parsed JSON location objects.
        """
        if not force and self.cached_location is not None:
            return

        locations = await self.client.get_locations(device_id=self.id, num_to_get=1)
        if not locations:
            self.cached_location = None
            return

        # Expect each location entry to already be a parsed mapping
        self.cached_location = locations[0] if isinstance(locations, list) else None
        self._last_refresh = datetime.now(timezone.utc)

    async def get_location(self, *, force: bool = False) -> Optional[Dict[str, Any]]:
        if force or self.cached_location is None:
            await self.refresh(force=force)
        return self.cached_location

    async def get_history(self, start: Optional[int] = None, end: Optional[int] = None, limit: int = -1) -> AsyncIterator[Dict[str, Any]]:
        """Async iterator over historical location objects (newest-first).

        Uses `client.get_locations(device_id=..., num_to_get=...)` and yields
        JSON mapping objects directly.
        """
        locations = await self.client.get_locations(device_id=self.id, num_to_get=limit)
        for loc in locations:
            yield loc

    async def lock(self, message: Optional[str] = None, passcode: Optional[str] = None) -> bool:
        base = "lock"
        if message:
            sanitized = " ".join(message.strip().split())
            for ch in ['"', "'", "`", ";"]:
                sanitized = sanitized.replace(ch, "")
            if len(sanitized) > 120:
                sanitized = sanitized[:120]
            if sanitized:
                base = f"lock {sanitized}"
        return await self.client.send_command(self.id, base)

    async def wipe(self, pin: Optional[str] = None, *, confirm: bool = False) -> bool:
        if not confirm:
            raise Exception("wipe() requires confirm=True to proceed (destructive action)")
        if not pin:
            raise Exception("wipe() requires a PIN: pass pin='yourPIN123'")
        if not all(ch.isalnum() and ord(ch) < 128 for ch in pin):
            raise Exception("PIN must contain only alphanumeric ASCII characters (a-z, A-Z, 0-9), no spaces")
        command = f"fmd delete {pin}"
        return await self.client.send_command(self.id, command)
