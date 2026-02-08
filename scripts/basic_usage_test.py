import asyncio
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

from lojack_api import LoJackClient


async def main() -> int:
    # Load credentials from scripts/.credentials using the local helper module
    try:
        spec = spec_from_file_location(
            "scripts.credentials", Path(__file__).parent / "credentials.py"
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("Failed to load local credentials module (spec missing)")
        creds_mod = module_from_spec(spec)
        assert creds_mod is not None
        spec.loader.exec_module(creds_mod)
        from typing import cast, Tuple

        creds = creds_mod.load_credentials(Path(__file__).parent / ".credentials")
        username, password = cast(Tuple[str, str], creds)
    except Exception as exc:
        print("Failed to load credentials:", exc)
        return 1

    try:
        client = await LoJackClient.create(username, password)
    except Exception as exc:
        print("Authentication failed:", exc)
        return 1

    async with client:
        try:
            devices = await client.list_devices()
        except Exception as exc:
            print("Failed to list devices:", exc)
            return 1

        print(f"Found {len(devices)} devices")

        for device in devices:
            print(f"- {device.name or 'Unnamed'} ({device.id})")

            # Print all device attributes
            print("  Device attributes:")
            for attr in vars(device.info):
                if attr != "raw":  # Skip raw data for now
                    value = getattr(device.info, attr)
                    print(f"    {attr}: {value}")

            # Print raw API data if available
            if device.info.raw:
                print("  Raw device data:")
                for key, value in device.info.raw.items():
                    print(f"    {key}: {value}")

            try:
                loc = await device.get_location()
            except Exception as exc:
                print("  Error fetching location:", exc)
                continue

            if loc:
                print("  Location attributes:")
                for attr in vars(loc):
                    if attr != "raw":  # Skip raw data for now
                        value = getattr(loc, attr)
                        print(f"    {attr}: {value}")

                # Print raw location data if available
                if loc.raw:
                    print("  Raw location data:")
                    for key, value in loc.raw.items():
                        print(f"    {key}: {value}")
            else:
                print("  No location available")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
