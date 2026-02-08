"""Probe Spireon event types, sort params, and alternate endpoints."""

import asyncio
import json
from pathlib import Path

from lojack_api import LoJackClient


from importlib.util import spec_from_file_location, module_from_spec


def load_creds() -> tuple[str, str]:
    try:
        spec = spec_from_file_location(
            "scripts.credentials", Path(__file__).parent / "credentials.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load local credentials module (spec missing)")
        creds_mod = module_from_spec(spec)
        assert creds_mod is not None
        spec.loader.exec_module(creds_mod)
        from typing import Tuple, cast

        creds = creds_mod.load_credentials(Path(__file__).parent / ".credentials")
        return cast(Tuple[str, str], creds)
    except Exception as exc:
        raise RuntimeError(f"Failed to load credentials: {exc}") from exc


async def main() -> None:
    u, p = load_creds()
    client = await LoJackClient.create(u, p)
    async with client:
        headers = await client._get_headers()
        transport = client._services_transport
        device_id = "16582627601048OW54PG"

        # 1. All event types in last 50 events
        print("=== All event types in last 50 events ===")
        r = await transport.request(
            "GET", f"/assets/{device_id}/events", params={"limit": 50}, headers=headers
        )
        if isinstance(r, dict):
            content = r.get("content") or []
            types: dict[str, str] = {}
            for ev in content:
                t = ev.get("type", "UNKNOWN")
                if t not in types:
                    types[t] = ev.get("date", "")
            for tp, dt in types.items():
                print(f"  {tp}: latest={dt}")

        # 2. Try LOCATION type filter
        for etype in ("LOCATION", "LOCATION_UPDATE", "HEARTBEAT", "PING", "GPS"):
            print(f"\n=== events type={etype} ===")
            try:
                r = await transport.request(
                    "GET",
                    f"/assets/{device_id}/events",
                    params={"limit": 3, "type": etype},
                    headers=headers,
                )
                if isinstance(r, dict):
                    content = r.get("content") or []
                    print(f"  total={r.get('total')} count={r.get('count')}")
                    for i, ev in enumerate(content):
                        print(f"  [{i}] type={ev.get('type')} date={ev.get('date')}")
            except Exception as exc:
                print(f"  ERROR: {exc}")

        # 3. Try sort params
        for sort_val in ("-date", "date:desc", "-timestamp"):
            print(f"\n=== events sort={sort_val} ===")
            try:
                r = await transport.request(
                    "GET",
                    f"/assets/{device_id}/events",
                    params={"limit": 3, "sort": sort_val},
                    headers=headers,
                )
                if isinstance(r, dict):
                    content = r.get("content") or []
                    for i, ev in enumerate(content):
                        print(f"  [{i}] type={ev.get('type')} date={ev.get('date')}")
            except Exception as exc:
                print(f"  ERROR: {exc}")

        # 4. Try includeInvisible or showAll params
        for param_name in (
            "includeInvisible",
            "showAll",
            "includeHidden",
            "includeAll",
        ):
            print(f"\n=== events {param_name}=true ===")
            try:
                r = await transport.request(
                    "GET",
                    f"/assets/{device_id}/events",
                    params={"limit": 3, param_name: "true"},
                    headers=headers,
                )
                if isinstance(r, dict):
                    content = r.get("content") or []
                    print(f"  total={r.get('total')} count={r.get('count')}")
                    for i, ev in enumerate(content):
                        print(f"  [{i}] type={ev.get('type')} date={ev.get('date')}")
            except Exception as exc:
                print(f"  ERROR: {exc}")

        # 5. Check raw asset for hidden fields with accountRef-based requests
        print("\n=== Full asset JSON field dump ===")
        r = await transport.request("GET", f"/assets/{device_id}", headers=headers)
        if isinstance(r, dict):
            # Print every key and its type+short value
            for k, v in r.items():
                sv = json.dumps(v, default=str) if not isinstance(v, str) else v
                print(f"  {k} ({type(v).__name__}): {sv[:150]}")


asyncio.run(main())
