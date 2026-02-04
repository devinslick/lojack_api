import asyncio
from pathlib import Path
from datetime import datetime, timezone

from lojack_api import LoJackClient


def load_credentials(path: Path) -> tuple[str | None, str | None]:
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")

    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        raise ValueError("Credentials file is empty")

    if any("=" in ln for ln in lines):
        data = {}
        for ln in lines:
            if "=" in ln:
                k, v = ln.split("=", 1)
                data[k.strip().lower()] = v.strip()
        return data.get("username"), data.get("password")

    if len(lines) >= 2:
        return lines[0], lines[1]

    raise ValueError("Credentials file must contain username and password")


async def main() -> int:
    cred_path = Path(__file__).parent / ".credentials"
    username, password = load_credentials(cred_path)
    # Validate credentials so mypy can narrow types for LoJackClient.create
    if username is None or password is None:
        print("Failed to load credentials: username or password not found in file")
        return 1

    client = await LoJackClient.create(username, password)

    async with client:
        devices = await client.list_devices()
        print(f"Found {len(devices)} devices")

        for device in devices:
            print(f"- {device.name or 'Unnamed'} ({device.id})")
            try:
                loc = await device.get_location()
            except Exception as exc:
                print("  Error fetching location:", exc)
                continue

            now = datetime.now(timezone.utc)

            if loc and loc.timestamp:
                # loc.timestamp is expected to be aware datetime
                ts = loc.timestamp
                delta = now - ts
                secs = int(delta.total_seconds())
                mins = secs / 60.0
                print(f"  Now (UTC): {now.isoformat()}")
                print(f"  Location timestamp: {ts.isoformat()}")
                print(f"  Delta: {secs} seconds ({mins:.2f} minutes)")
            else:
                print("  No timestamp available for location")

            # Show raw locationLastReported if present in the returned Location
            raw = getattr(loc, "raw", {}) if loc else {}
            if raw:
                if "locationLastReported" in raw:
                    print(
                        f"  raw['locationLastReported']: {raw['locationLastReported']}"
                    )
                elif "dateCreated" in raw:
                    print(f"  raw['dateCreated']: {raw['dateCreated']}")

            # Also fetch and print the raw /assets and /assets/{id}/events responses
            # to compare what the API is returning directly.
            try:
                asset_raw = await client._services_transport.request(
                    "GET", f"/assets/{device.id}", headers=await client._get_headers()
                )
                print(
                    "  /assets response keys:",
                    (
                        list(asset_raw.keys())
                        if isinstance(asset_raw, dict)
                        else type(asset_raw)
                    ),
                )
                # Print common timestamp-like fields if present
                for k in (
                    "locationLastReported",
                    "lastLocation",
                    "lastUpdated",
                    "lastUpdatedDate",
                    "lastEventDateTime",
                ):
                    if isinstance(asset_raw, dict) and k in asset_raw:
                        print(f"    asset[{k}]: {asset_raw[k]}")
            except Exception as exc:
                print("  Error fetching raw asset:", exc)

            try:
                events_raw = await client._services_transport.request(
                    "GET",
                    f"/assets/{device.id}/events",
                    params={"limit": 1},
                    headers=await client._get_headers(),
                )
                print(
                    "  /assets/{id}/events response keys:",
                    (
                        list(events_raw.keys())
                        if isinstance(events_raw, dict)
                        else type(events_raw)
                    ),
                )
                if isinstance(events_raw, dict):
                    content = (
                        events_raw.get("content")
                        or events_raw.get("events")
                        or events_raw.get("locations")
                        or events_raw.get("history")
                    )
                    print(
                        "    events count:",
                        len(content) if content is not None else "unknown",
                    )
                    if content:
                        print("    first event keys:", list(content[0].keys()))
                        # Show candidate timestamp fields on the first event
                        for k in ("date", "eventDateTime", "timestamp", "dateTime"):
                            if k in content[0]:
                                print(f"      event[{k}]: {content[0][k]}")
            except Exception as exc:
                print("  Error fetching raw events:", exc)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
