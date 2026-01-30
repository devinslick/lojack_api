import asyncio
from pathlib import Path

from lojack_api import LoJackClient


def load_credentials(path: Path) -> tuple[str | None, str | None]:
    """Load credentials from a simple key=value file or two-line file.

    Accepts either:
    username=...\npassword=...
    or two lines: first is username, second is password.
    """
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")

    lines = [
        ln.strip()
        for ln in path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        raise ValueError("Credentials file is empty")

    # key=value format
    if any("=" in ln for ln in lines):
        data = {}
        for ln in lines:
            if "=" in ln:
                k, v = ln.split("=", 1)
                data[k.strip().lower()] = v.strip()
        return data.get("username"), data.get("password")

    # fallback: assume first is username, second is password
    if len(lines) >= 2:
        return lines[0], lines[1]

    raise ValueError("Credentials file must contain username and password")


async def main() -> int:
    # Load credentials from scripts/.credentials
    cred_path = Path(__file__).parent / ".credentials"
    try:
        username, password = load_credentials(cred_path)
        if username is None or password is None:
            print("Failed to load credentials: username or password not found in file")
            return 1
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
