import asyncio
from pathlib import Path
from lojack_clients import LoJackClient


def load_credentials(path: Path):
    """Load credentials from a simple key=value file or two-line file.

    Accepts either:
    username=...\npassword=...
    or two lines: first is username, second is password.
    """
    if not path.exists():
        raise FileNotFoundError(f"Credentials file not found: {path}")

    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.strip().startswith("#")]
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


async def main():
    # Load credentials from scripts/.credentials
    cred_path = Path(__file__).parent / ".credentials"
    try:
        username, password = load_credentials(cred_path)
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
            try:
                loc = await device.get_location()
            except Exception as exc:
                print("  Error fetching location:", exc)
                continue

            if loc:
                lat = getattr(loc, "latitude", None)
                lon = getattr(loc, "longitude", None)
                print(f"  Location: {lat}, {lon}")
            else:
                print("  No location available")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
