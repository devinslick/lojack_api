"""Poll locations and optionally request fresh location updates.

This script helps diagnose stale location data issues by:
1. Showing the current location timestamp and age
2. Optionally sending a "locate" command to request fresh data
3. Polling to detect when fresh data arrives

Usage:
    python poll_locations.py              # Show current location ages
    python poll_locations.py --locate     # Request fresh location, then poll
    python poll_locations.py --poll 30    # Poll every 30s without locate command
"""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

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


def format_age(delta_seconds: float) -> str:
    """Format age in a human-readable way."""
    if delta_seconds < 60:
        return f"{delta_seconds:.0f}s"
    elif delta_seconds < 3600:
        return f"{delta_seconds / 60:.1f}m"
    else:
        return f"{delta_seconds / 3600:.1f}h"


async def get_location_timestamp(client: LoJackClient, device_id: str) -> datetime | None:
    """Get the location timestamp using the public API."""
    try:
        location = await client.get_current_location(device_id)
        if location:
            return location.timestamp
    except Exception:
        pass
    return None


async def poll_device_location(
    client: LoJackClient,
    device,
    initial_timestamp: datetime | None,
    poll_interval: int,
    max_wait: int,
) -> bool:
    """Poll for location updates until timestamp changes or timeout.

    Returns True if fresh data was received, False if timed out.
    """
    start_time = datetime.now(timezone.utc)
    poll_count = 0

    while True:
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        if elapsed >= max_wait:
            print(f"    Timeout after {elapsed:.0f}s - no fresh data received")
            return False

        poll_count += 1
        current_ts = await get_location_timestamp(client, device.id)
        now = datetime.now(timezone.utc)

        if current_ts:
            age = (now - current_ts).total_seconds()

            # Check if timestamp changed (or first timestamp arrived when none existed)
            if initial_timestamp is None:
                # No baseline - first non-None timestamp is success
                print(f"    [Poll #{poll_count}] First location data received!")
                print(f"    Timestamp: {current_ts.isoformat()} (age: {format_age(age)})")
                return True
            elif current_ts > initial_timestamp:
                print(f"    [Poll #{poll_count}] Fresh data received!")
                print(f"    New timestamp: {current_ts.isoformat()}")
                print(f"    Age: {format_age(age)} (was {format_age((now - initial_timestamp).total_seconds())})")
                return True

            print(f"    [Poll #{poll_count}] Timestamp: {current_ts.isoformat()} (age: {format_age(age)})")
        else:
            print(f"    [Poll #{poll_count}] No timestamp available")

        await asyncio.sleep(poll_interval)


async def show_device_status(client: LoJackClient, device, verbose: bool = False) -> datetime | None:
    """Show current device location status. Returns the timestamp."""
    print(f"\n{'='*60}")
    print(f"Device: {device.name or 'Unnamed'} ({device.id})")
    print(f"{'='*60}")

    now = datetime.now(timezone.utc)

    # Get location through the library
    try:
        loc = await device.get_location(force=True)
    except Exception as exc:
        print(f"  Error fetching location: {exc}")
        return None

    if loc and loc.timestamp:
        ts = loc.timestamp
        delta = (now - ts).total_seconds()
        print(f"  Current time (UTC): {now.isoformat()}")
        print(f"  Location timestamp: {ts.isoformat()}")
        print(f"  Age: {format_age(delta)}")

        if loc.latitude and loc.longitude:
            print(f"  Position: {loc.latitude:.6f}, {loc.longitude:.6f}")
    else:
        print("  No timestamp available for location")
        ts = None

    if verbose:
        # Show raw API response details
        try:
            asset_raw = await client._services_transport.request(
                "GET", f"/assets/{device.id}", headers=await client._get_headers()
            )
            if isinstance(asset_raw, dict):
                print("\n  Raw API fields:")
                for k in ("locationLastReported", "lastUpdated", "lastEventDateTime"):
                    if k in asset_raw:
                        print(f"    {k}: {asset_raw[k]}")
        except Exception as exc:
            print(f"  Error fetching raw asset: {exc}")

    return ts


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Poll device locations and optionally request fresh updates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python poll_locations.py                  Show current location ages
  python poll_locations.py --locate         Request fresh location, then poll
  python poll_locations.py --poll 30        Poll every 30s (no locate command)
  python poll_locations.py --locate --wait 120  Request locate, wait up to 2 min

Note:
  The Spireon REST API may return stale location data (30-76+ minutes old).
  The mobile app uses the "locate" command to request fresh data from the device.
  Use --locate to trigger a location update request and poll for fresh data.
        """
    )
    parser.add_argument(
        "--locate",
        action="store_true",
        help="Send a 'locate' command to request fresh location from device"
    )
    parser.add_argument(
        "--poll",
        type=int,
        metavar="SECONDS",
        help="Poll interval in seconds (default: 10 with --locate, otherwise single check)"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Maximum time to wait for fresh data (default: 300s / 5 min)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show additional raw API response details"
    )

    args = parser.parse_args()

    # Set default poll interval
    if args.poll is None:
        poll_interval = 10 if args.locate else 0
    else:
        poll_interval = args.poll

    cred_path = Path(__file__).parent / ".credentials"
    try:
        username, password = load_credentials(cred_path)
    except Exception as exc:
        print(f"Failed to load credentials: {exc}")
        return 1

    if username is None or password is None:
        print("Failed to load credentials: username or password not found in file")
        return 1

    print("Connecting to LoJack API...")
    client = await LoJackClient.create(username, password)

    async with client:
        devices = await client.list_devices()
        print(f"Found {len(devices)} device(s)")

        for device in devices:
            # Show current status
            initial_ts = await show_device_status(client, device, verbose=args.verbose)

            if args.locate:
                print("\n  Sending 'locate' command...")
                try:
                    success = await device.request_location_update()
                    if success:
                        print("  Locate command accepted. Waiting for device to report...")
                    else:
                        print("  Locate command may not have been accepted")
                except Exception as exc:
                    print(f"  Error sending locate command: {exc}")
                    continue

                # Poll for fresh data
                if poll_interval > 0:
                    print(f"  Polling every {poll_interval}s (max wait: {args.wait}s)...")
                    await poll_device_location(
                        client, device, initial_ts, poll_interval, args.wait
                    )

            elif poll_interval > 0:
                # Continuous polling without locate command
                print(f"\n  Polling every {poll_interval}s (Ctrl+C to stop)...")
                try:
                    while True:
                        await asyncio.sleep(poll_interval)
                        await show_device_status(client, device, verbose=args.verbose)
                except KeyboardInterrupt:
                    print("\n  Stopped.")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
