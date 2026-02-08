"""Diagnostic script to identify why location data is stale.

Polls location data from multiple API paths, waits 30 seconds, then
polls again to compare timestamps and identify the freshest source.
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lojack_api import LoJackClient


def load_credentials(path: Path) -> tuple[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")
    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if any("=" in ln for ln in lines):
        data: dict[str, str] = {}
        for ln in lines:
            if "=" in ln:
                k, v = ln.split("=", 1)
                data[k.strip().lower()] = v.strip()
        u, p = data.get("username"), data.get("password")
        if u and p:
            return u, p
    elif len(lines) >= 2:
        return lines[0], lines[1]
    raise ValueError("Credentials file must contain username and password")


def ts_delta(ts_str: str | None) -> str:
    """Return human-readable delta between now-UTC and a timestamp string."""
    if not ts_str:
        return "(no timestamp)"
    from lojack_api.models import _parse_timestamp

    dt = _parse_timestamp(ts_str)
    if dt is None:
        return f"(unparseable: {ts_str})"
    delta = datetime.now(timezone.utc) - dt
    secs = int(delta.total_seconds())
    return f"{secs}s ago ({secs / 60:.1f} min) — {ts_str}"


async def probe_api(client: LoJackClient, device_id: str, label: str) -> dict[str, Any]:
    """Probe all known API endpoints and print timestamp-bearing fields."""
    headers = await client._get_headers()
    transport = client._services_transport
    results: dict[str, Any] = {}

    now = datetime.now(timezone.utc)
    print(f"\n{'='*70}")
    print(f"[{label}] Probe at {now.isoformat()}")
    print(f"{'='*70}")

    # 1. GET /assets/{id}  (the "asset" endpoint used by get_current_location)
    print("\n--- GET /assets/{id} ---")
    try:
        asset = await transport.request("GET", f"/assets/{device_id}", headers=headers)
        results["asset"] = asset
        if isinstance(asset, dict):
            print(
                f"  locationLastReported : {ts_delta(asset.get('locationLastReported'))}"
            )
            print(f"  statusStartDate     : {ts_delta(asset.get('statusStartDate'))}")
            print(f"  lastUpdated         : {ts_delta(asset.get('lastUpdated'))}")
            ll = asset.get("lastLocation", {})
            print(f"  lastLocation        : lat={ll.get('lat')}, lng={ll.get('lng')}")
            print(f"  speed               : {asset.get('speed')}")
            print(f"  status              : {asset.get('status')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 2. GET /assets/{id}/events?limit=1  (latest event — used by refresh())
    print("\n--- GET /assets/{id}/events?limit=1 ---")
    try:
        events1 = await transport.request(
            "GET", f"/assets/{device_id}/events", params={"limit": 1}, headers=headers
        )
        results["events_limit1"] = events1
        if isinstance(events1, dict):
            content = (
                events1.get("content")
                or events1.get("events")
                or events1.get("locations")
                or []
            )
            print(f"  total: {events1.get('total')}, count: {events1.get('count')}")
            if content:
                ev = content[0]
                print(f"  event[0].date       : {ts_delta(ev.get('date'))}")
                print(f"  event[0].type       : {ev.get('type')}")
                loc = ev.get("location", {})
                print(
                    f"  event[0].location   : lat={loc.get('lat')}, lng={loc.get('lng')}"
                )
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 3. GET /assets/{id}/events?limit=5  (check if there are newer events beyond index 0)
    print("\n--- GET /assets/{id}/events?limit=5 ---")
    try:
        events5 = await transport.request(
            "GET", f"/assets/{device_id}/events", params={"limit": 5}, headers=headers
        )
        results["events_limit5"] = events5
        if isinstance(events5, dict):
            content = (
                events5.get("content")
                or events5.get("events")
                or events5.get("locations")
                or []
            )
            print(f"  total: {events5.get('total')}, count: {events5.get('count')}")
            for i, ev in enumerate(content[:5]):
                print(
                    f"  event[{i}] type={ev.get('type'):<20s} date={ts_delta(ev.get('date'))}"
                )
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 4. GET /assets/{id}/locations  (alternate endpoint — may or may not exist)
    print("\n--- GET /assets/{id}/locations ---")
    try:
        locs = await transport.request(
            "GET",
            f"/assets/{device_id}/locations",
            params={"limit": 3},
            headers=headers,
        )
        results["locations"] = locs
        if isinstance(locs, dict):
            content = locs.get("content") or locs.get("locations") or []
            print(f"  response keys: {list(locs.keys())}")
            for i, item in enumerate(content[:3]):
                print(f"  loc[{i}]: {json.dumps(item, default=str)[:200]}")
        elif isinstance(locs, list):
            for i, item in enumerate(locs[:3]):
                print(f"  loc[{i}]: {json.dumps(item, default=str)[:200]}")
        else:
            print(f"  response: {str(locs)[:200]}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 5. GET /assets/{id}/currentLocation  (alternate endpoint)
    print("\n--- GET /assets/{id}/currentLocation ---")
    try:
        cur = await transport.request(
            "GET", f"/assets/{device_id}/currentLocation", headers=headers
        )
        results["currentLocation"] = cur
        if isinstance(cur, dict):
            print(f"  response keys: {list(cur.keys())}")
            print(f"  lat={cur.get('lat')}, lng={cur.get('lng')}")
            for k in ("date", "timestamp", "dateTime", "locationLastReported"):
                if k in cur:
                    print(f"  {k}: {ts_delta(cur.get(k))}")
        else:
            print(f"  response: {str(cur)[:300]}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 6. GET /assets/{id}/events with startDate = 1 hour ago (date-range query)
    from datetime import timedelta

    one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.000+0000"
    )
    print(f"\n--- GET /assets/{{id}}/events?startDate={one_hour_ago}&limit=10 ---")
    try:
        events_recent = await transport.request(
            "GET",
            f"/assets/{device_id}/events",
            params={"startDate": one_hour_ago, "limit": 10},
            headers=headers,
        )
        results["events_recent"] = events_recent
        if isinstance(events_recent, dict):
            content = (
                events_recent.get("content")
                or events_recent.get("events")
                or events_recent.get("locations")
                or []
            )
            print(
                f"  total: {events_recent.get('total')}, count: {events_recent.get('count')}"
            )
            for i, ev in enumerate(content[:10]):
                print(
                    f"  event[{i}] type={ev.get('type'):<20s} date={ts_delta(ev.get('date'))}"
                )
        else:
            print(f"  response: {str(events_recent)[:300]}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # 7. GET /assets  (list all — check if bulk endpoint has different lastLocation)
    print("\n--- GET /assets (list all) ---")
    try:
        all_assets = await transport.request("GET", "/assets", headers=headers)
        results["all_assets_meta"] = "fetched"
        if isinstance(all_assets, dict):
            items = all_assets.get("content") or all_assets.get("assets") or []
            for item in items:
                if isinstance(item, dict) and item.get("id") == device_id:
                    print(
                        f"  locationLastReported : {ts_delta(item.get('locationLastReported'))}"
                    )
                    print(
                        f"  statusStartDate     : {ts_delta(item.get('statusStartDate'))}"
                    )
                    ll = item.get("lastLocation", {})
                    print(
                        f"  lastLocation        : lat={ll.get('lat')}, lng={ll.get('lng')}"
                    )
                    print(f"  speed               : {item.get('speed')}")
                    print(f"  status              : {item.get('status')}")
    except Exception as exc:
        print(f"  ERROR: {exc}")

    return results


async def main() -> int:
    # Ensure we can import the local credentials helper when running as a script
    import sys
    from pathlib import Path as _P

    sys.path.insert(0, str(_P(__file__).parent))
    from credentials import load_credentials as _load_credentials

    try:
        username, password = _load_credentials(_P(__file__).parent / ".credentials")
    except Exception as exc:
        print("Failed to load credentials:", exc)
        return 1

    client = await LoJackClient.create(username, password)

    async with client:
        devices = await client.list_devices()
        if not devices:
            print("No devices found")
            return 1

        device = devices[0]
        device_id = device.id
        print(f"Device: {device.name} ({device_id})")

        # ---- First poll ----
        r1 = await probe_api(client, device_id, "POLL 1")

        # ---- Wait 30 seconds ----
        print("\n\n>>> Waiting 30 seconds...\n")
        await asyncio.sleep(30)

        # ---- Second poll ----
        r2 = await probe_api(client, device_id, "POLL 2")

        # ---- Summary ----
        print("\n" + "=" * 70)
        print("SUMMARY: Did any timestamps change between polls?")
        print("=" * 70)

        def get_ts(results: dict[str, Any], key: str) -> str | None:
            if key == "asset.locationLastReported":
                a = results.get("asset")
                return a.get("locationLastReported") if isinstance(a, dict) else None
            if key == "events.first.date":
                e = results.get("events_limit1")
                if isinstance(e, dict):
                    c = e.get("content") or e.get("events") or []
                    return c[0].get("date") if c else None
            return None

        for label in ("asset.locationLastReported", "events.first.date"):
            t1 = get_ts(r1, label)
            t2 = get_ts(r2, label)
            changed = "YES ✓" if t1 != t2 else "NO (same stale value)"
            print(f"  {label}:")
            print(f"    Poll 1: {t1}")
            print(f"    Poll 2: {t2}")
            print(f"    Changed? {changed}")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
