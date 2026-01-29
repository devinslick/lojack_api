from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class Device:
    id: str
    name: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
    last_seen: Optional[datetime] = None

    def update_from_api(self, data: Dict[str, Any]) -> None:
        self.raw = data
        self.name = data.get("name", self.name)
        ts = data.get("last_seen")
        if ts:
            try:
                self.last_seen = datetime.fromisoformat(ts)
            except Exception:
                pass


class Vehicle(Device):
    vin: Optional[str] = None

    def update_from_api(self, data: Dict[str, Any]) -> None:
        super().update_from_api(data)
        self.vin = data.get("vin")
