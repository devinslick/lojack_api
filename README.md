# lojack_api

An async Python client library for the Spireon LoJack API, designed for Home Assistant integrations.

[![Tests](https://github.com/devinslick/lojack_api/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/devinslick/lojack_api/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/devinslick/lojack_api/branch/main/graph/badge.svg?token=K97PlD4IU4)](https://codecov.io/gh/devinslick/lojack_api)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/lojack_api)](https://pypi.org/project/lojack_api/)

## Features

- **Async-first design** - Built with `asyncio` and `aiohttp` for non-blocking I/O
- **No httpx dependency** - Uses `aiohttp` to avoid version conflicts with Home Assistant
- **Spireon LoJack API** - Full support for the Spireon identity and services APIs
- **Session management** - Automatic token refresh and session resumption support
- **Type hints** - Full typing support with `py.typed` marker
- **Clean device abstractions** - Device and Vehicle wrappers with convenient methods

## Installation

```bash
# From the repository
pip install .

# With development dependencies
pip install .[dev]
```

## Quick Start

### Basic Usage

```python
import asyncio
from lojack_api import LoJackClient

async def main():
    # Create and authenticate (uses default Spireon URLs)
    async with await LoJackClient.create(
        "your_username",
        "your_password"
    ) as client:
        # List all devices/vehicles
        devices = await client.list_devices()

        for device in devices:
            print(f"Device: {device.name} ({device.id})")

            # Get current location
            location = await device.get_location()
            if location:
                print(f"  Location: {location.latitude}, {location.longitude}")

asyncio.run(main())
```

### Session Resumption (for Home Assistant)

For Home Assistant integrations, you can persist authentication across restarts:

```python
from lojack_api import LoJackClient, AuthArtifacts

# First time - login and save auth
async def initial_login(username, password):
    client = await LoJackClient.create(username, password)
    auth_data = client.export_auth().to_dict()
    # Save auth_data to Home Assistant storage
    await client.close()
    return auth_data

# Later - resume without re-entering password
async def resume_session(auth_data, username=None, password=None):
    auth = AuthArtifacts.from_dict(auth_data)
    # Pass credentials for auto-refresh if token expires
    client = await LoJackClient.from_auth(auth, username=username, password=password)
    return client
```

### Using External aiohttp Session

For Home Assistant integrations, pass the shared session:

```python
from aiohttp import ClientSession
from lojack_api import LoJackClient

async def setup(hass_session: ClientSession, username, password):
    client = await LoJackClient.create(
        username,
        password,
        session=hass_session  # Won't be closed when client closes
    )
    return client
```

### Working with Vehicles

Vehicles have additional properties:

```python
from lojack_api import Vehicle

async def vehicle_example(client):
    devices = await client.list_devices()

    for device in devices:
        if isinstance(device, Vehicle):
            print(f"Vehicle: {device.name}")
            print(f"  VIN: {device.vin}")
            print(f"  Make: {device.make} {device.model} ({device.year})")
```

### Requesting Fresh Location Data

The Spireon REST API may return stale location data (30-76+ minutes old) because
devices report periodically, not continuously. Two methods are available to
request on-demand location updates:

#### Method Comparison

| Method | Returns | Use Case |
|--------|---------|----------|
| `request_location_update()` | `bool` | Fire-and-forget; scripts, simple polling |
| `request_fresh_location()` | `datetime \| None` | Non-blocking with baseline; Home Assistant |

#### `request_location_update()` -> bool

Sends a "locate" command to the device. Returns `True` if the command was
accepted by the API. This is a fire-and-forget method - you must poll
separately to detect when fresh data arrives.

```python
# Simple usage - send command and poll manually
success = await device.request_location_update()
if success:
    await asyncio.sleep(30)  # Wait for device to respond
    location = await device.get_location(force=True)
```

#### `request_fresh_location()` -> datetime | None

Sends a "locate" command and returns the current location timestamp as a
baseline for comparison. This is the recommended method for Home Assistant
integrations because it's non-blocking and provides a reference point to
detect when fresh data arrives.

```python
from datetime import datetime, timezone

# In a service call or button handler
baseline_ts = await device.request_fresh_location()

# Later, in your DataUpdateCoordinator's _async_update_data:
location = await device.get_location(force=True)
if location and location.timestamp:
    # Check if we received fresh data since the locate command
    if baseline_ts and location.timestamp > baseline_ts:
        print("Fresh location received!")
    age = (datetime.now(timezone.utc) - location.timestamp).total_seconds()
```

**Returns:**
- `datetime` - The location timestamp before the locate command was sent
- `None` - If no prior location was available

#### Location History

```python
# Get location history
async for location in device.get_history(limit=100):
    print(f"{location.timestamp}: {location.latitude}, {location.longitude}")
```

#### Troubleshooting Script

For debugging location freshness issues:

```bash
# Show current location ages
python scripts/poll_locations.py

# Request fresh location and monitor for updates
python scripts/poll_locations.py --locate

# Poll continuously every 30 seconds
python scripts/poll_locations.py --poll 30
```

## API Reference

### LoJackClient

The main entry point for the API.

```python
# Factory methods (using default Spireon URLs)
client = await LoJackClient.create(username, password)
client = await LoJackClient.from_auth(auth_artifacts)

# With custom URLs
client = await LoJackClient.create(
    username,
    password,
    identity_url="https://identity.spireon.com",
    services_url="https://services.spireon.com/v0/rest"
)

# Properties
client.is_authenticated  # bool
client.user_id           # Optional[str]

# Methods
devices = await client.list_devices()           # List[Device | Vehicle]
device = await client.get_device(device_id)     # Device | Vehicle
locations = await client.get_locations(device_id, limit=10)
success = await client.send_command(device_id, "locate")
auth = client.export_auth()                     # AuthArtifacts
await client.close()
```

### Device

Wrapper for tracked devices.

```python
# Properties
device.id            # str
device.name          # Optional[str]
device.info          # DeviceInfo
device.last_seen     # Optional[datetime]
device.cached_location  # Optional[Location]

# Methods
await device.refresh(force=True)              # Refresh cached location from API
location = await device.get_location(force=False)  # Get location (from cache or API)
async for loc in device.get_history(limit=100):    # Iterate location history
    ...

# Location update methods
success = await device.request_location_update()   # bool - fire-and-forget locate
baseline = await device.request_fresh_location()   # datetime|None - locate + baseline

# Properties
device.location_timestamp  # datetime|None - cached location's timestamp
```

### Vehicle (extends Device)

Additional properties for vehicles.

```python
# Properties
vehicle.vin           # Optional[str]
vehicle.make          # Optional[str]
vehicle.model         # Optional[str]
vehicle.year          # Optional[int]
vehicle.license_plate # Optional[str]
vehicle.odometer      # Optional[float]
```

### Data Models

```python
from lojack_api import Location, DeviceInfo, VehicleInfo

# Location - Core fields
location.latitude   # Optional[float]
location.longitude  # Optional[float]
location.timestamp  # Optional[datetime]
location.accuracy   # Optional[float] - GPS accuracy in METERS (for HA gps_accuracy)
location.speed      # Optional[float]
location.heading    # Optional[float]
location.address    # Optional[str]

# Note on accuracy: The API may return HDOP values or quality strings.
# These are automatically converted to meters for Home Assistant compatibility:
# - HDOP values (1-15) are multiplied by 5 to get approximate meters
# - Quality strings ("GOOD", "POOR", etc.) are mapped to reasonable meter values
# - Values > 15 are assumed to already be in meters

# Location - Extended telemetry (from events)
location.odometer        # Optional[float] - Vehicle odometer reading
location.battery_voltage # Optional[float] - Battery voltage
location.engine_hours    # Optional[float] - Engine hours
location.distance_driven # Optional[float] - Total distance driven
location.signal_strength # Optional[float] - Signal strength (0.0 to 1.0)
location.gps_fix_quality # Optional[str] - GPS quality (e.g., "GOOD", "POOR")
location.event_type      # Optional[str] - Event type (e.g., "SLEEP_ENTER")
location.event_id        # Optional[str] - Unique event identifier

# Location - Raw data
location.raw        # Dict[str, Any] - Original API response
```

### Exceptions

```python
from lojack_api import (
    LoJackError,           # Base exception
    AuthenticationError,   # 401 errors, invalid credentials
    AuthorizationError,    # 403 errors, permission denied
    ApiError,              # Other API errors (has status_code)
    ConnectionError,       # Network connectivity issues
    TimeoutError,          # Request timeouts
    DeviceNotFoundError,   # Device not found (has device_id)
    CommandError,          # Command failed (has command, device_id)
)
```

### Spireon API Details

The library uses the Spireon LoJack API:

- **Identity Service**: `https://identity.spireon.com` - For authentication
- **Services API**: `https://services.spireon.com/v0/rest` - For device/asset management

Authentication uses HTTP Basic Auth with the following headers:
- `X-Nspire-Apptoken` - Application token
- `X-Nspire-Correlationid` - Unique request ID
- `X-Nspire-Usertoken` - User token (after authentication)

## Development

```bash
# Install dev dependencies
pip install .[dev]

# Run tests
pytest

# Run tests with coverage
pytest --cov=lojack_api

# Type checking
mypy lojack_api

# Linting
# Preferred: ruff for quick fixes
ruff check .

# Use flake8 for strict style checks (reports shown in CI)
# Match ruff's line length setting
flake8 lojack_api/ tests/ --count --show-source --statistics --max-line-length=100
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! This library is designed to be vendored into Home Assistant integrations to avoid dependency conflicts.

## Credits

This library was inspired by the original [lojack-clients](https://github.com/scorgn/lojack-clients) package and uses the Spireon LoJack API endpoints.
