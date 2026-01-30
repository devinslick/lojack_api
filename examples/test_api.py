#!/usr/bin/env python3
"""Comprehensive test script for the LoJack API.

This script tests all API functionality and displays raw responses
to help debug issues like missing geolocation data.

Usage:
    python examples/test_api.py <username> <password>

Or set environment variables:
    LOJACK_USERNAME=your_username
    LOJACK_PASSWORD=your_password
    python examples/test_api.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

# Add parent directory to path for local development
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lojack_api import (
    IDENTITY_URL,
    SERVICES_URL,
    AuthenticationError,
    Device,
    LoJackClient,
    Vehicle,
)


def print_separator(title: str = "") -> None:
    """Print a visual separator."""
    if title:
        print(f"\n{'=' * 60}")
        print(f"  {title}")
        print(f"{'=' * 60}")
    else:
        print("-" * 60)


def print_dict(data: dict[str, Any], indent: int = 2) -> None:
    """Pretty print a dictionary."""
    print(json.dumps(data, indent=indent, default=str))


async def test_authentication(username: str, password: str) -> LoJackClient | None:
    """Test authentication and return client if successful."""
    print_separator("AUTHENTICATION TEST")
    print(f"Identity URL: {IDENTITY_URL}")
    print(f"Services URL: {SERVICES_URL}")
    print(f"Username: {username}")
    print(f"Password: {'*' * len(password)}")

    try:
        client = await LoJackClient.create(username, password)
        print("\n[SUCCESS] Authentication successful!")
        print(f"  User ID: {client.user_id}")
        print(f"  Is Authenticated: {client.is_authenticated}")

        # Show auth artifacts (for debugging session resumption)
        auth = client.export_auth()
        if auth:
            print(f"  Token (first 50 chars): {auth.access_token[:50]}...")
            print(f"  Expires At: {auth.expires_at}")

        return client

    except AuthenticationError as e:
        print(f"\n[FAILED] Authentication failed: {e}")
        return None
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {type(e).__name__}: {e}")
        return None


async def test_list_devices(client: LoJackClient) -> list:
    """Test listing all devices and show raw data."""
    print_separator("LIST DEVICES TEST")

    try:
        # First, get raw response to see what API returns
        print("\n--- Raw API Response ---")
        headers = await client._get_headers()
        raw_data = await client._services_transport.request(
            "GET", "/assets", headers=headers
        )
        print_dict(raw_data if isinstance(raw_data, dict) else {"response": raw_data})

        # Now get parsed devices
        print("\n--- Parsed Devices ---")
        devices = await client.list_devices()
        print(f"\nFound {len(devices)} device(s)")

        for i, device in enumerate(devices):
            print(f"\n[Device {i + 1}]")
            print(f"  ID: {device.id}")
            print(f"  Name: {device.name}")
            print(f"  Type: {type(device).__name__}")
            print(f"  Last Seen: {device.last_seen}")

            if isinstance(device, Vehicle):
                print(f"  VIN: {device.vin}")
                print(f"  Make: {device.make}")
                print(f"  Model: {device.model}")
                print(f"  Year: {device.year}")
                print(f"  License Plate: {device.license_plate}")
                print(f"  Odometer: {device.odometer}")

            # Show raw info
            print("\n  --- Raw Device Info ---")
            print_dict(device.info.raw)

        return devices

    except Exception as e:
        print(f"\n[ERROR] Failed to list devices: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def test_device_locations(client: LoJackClient, device: Device) -> None:
    """Test getting locations for a device."""
    print_separator(f"LOCATION TEST: {device.name or device.id}")

    try:
        # First, try the /events endpoint (what we currently use)
        print("\n--- Testing /events endpoint ---")
        headers = await client._get_headers()
        params = {"assetId": device.id, "limit": 10}

        try:
            events_data = await client._services_transport.request(
                "GET", "/events", params=params, headers=headers
            )
            print("Raw /events response:")
            print_dict(events_data if isinstance(events_data, dict) else {"response": events_data})
        except Exception as e:
            print(f"  /events failed: {e}")

        # Try alternative endpoints that might have location data
        print("\n--- Testing /assets/{id} endpoint (single asset) ---")
        try:
            asset_data = await client._services_transport.request(
                "GET", f"/assets/{device.id}", headers=headers
            )
            print("Raw /assets/{id} response:")
            print_dict(asset_data if isinstance(asset_data, dict) else {"response": asset_data})
        except Exception as e:
            print(f"  /assets/{{id}} failed: {e}")

        # Try location-specific endpoint
        print("\n--- Testing /assets/{id}/location endpoint ---")
        try:
            location_data = await client._services_transport.request(
                "GET", f"/assets/{device.id}/location", headers=headers
            )
            print("Raw /assets/{id}/location response:")
            print_dict(location_data if isinstance(location_data, dict) else {"response": location_data})
        except Exception as e:
            print(f"  /assets/{{id}}/location failed: {e}")

        # Try locations endpoint
        print("\n--- Testing /assets/{id}/locations endpoint ---")
        try:
            locations_data = await client._services_transport.request(
                "GET", f"/assets/{device.id}/locations", params={"limit": 10}, headers=headers
            )
            print("Raw /assets/{id}/locations response:")
            print_dict(locations_data if isinstance(locations_data, dict) else {"response": locations_data})
        except Exception as e:
            print(f"  /assets/{{id}}/locations failed: {e}")

        # Try history endpoint
        print("\n--- Testing /assets/{id}/history endpoint ---")
        try:
            # Get last 24 hours
            end = datetime.now(timezone.utc)
            start = end - timedelta(hours=24)
            history_params = {
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "limit": 10,
            }
            history_data = await client._services_transport.request(
                "GET", f"/assets/{device.id}/history", params=history_params, headers=headers
            )
            print("Raw /assets/{id}/history response:")
            print_dict(history_data if isinstance(history_data, dict) else {"response": history_data})
        except Exception as e:
            print(f"  /assets/{{id}}/history failed: {e}")

        # Now test our parsed location method
        print("\n--- Parsed Locations (via client.get_locations) ---")
        locations = await client.get_locations(device.id, limit=5)
        print(f"Got {len(locations)} parsed location(s)")

        for j, loc in enumerate(locations):
            print(f"\n  [Location {j + 1}]")
            print(f"    Latitude: {loc.latitude}")
            print(f"    Longitude: {loc.longitude}")
            print(f"    Timestamp: {loc.timestamp}")
            print(f"    Speed: {loc.speed}")
            print(f"    Heading: {loc.heading}")
            print(f"    Accuracy: {loc.accuracy}")
            print(f"    Address: {loc.address}")
            print(f"    Raw data keys: {list(loc.raw.keys())}")

        # Test device wrapper location method
        print("\n--- Device Wrapper Location (via device.get_location) ---")
        location = await device.get_location(force=True)
        if location:
            print(f"  Latitude: {location.latitude}")
            print(f"  Longitude: {location.longitude}")
            print(f"  Timestamp: {location.timestamp}")
        else:
            print("  No location available")

    except Exception as e:
        print(f"\n[ERROR] Location test failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


async def test_available_endpoints(client: LoJackClient) -> None:
    """Try to discover available API endpoints."""
    print_separator("ENDPOINT DISCOVERY")

    headers = await client._get_headers()

    # Common Spireon endpoints to try
    endpoints = [
        "/assets",
        "/events",
        "/commands",
        "/geofences",
        "/alerts",
        "/users/me",
        "/account",
        "/devices",
        "/vehicles",
    ]

    print("Testing common endpoints...")
    for endpoint in endpoints:
        try:
            data = await client._services_transport.request(
                "GET", endpoint, headers=headers
            )
            status = "OK"
            if isinstance(data, dict):
                keys = list(data.keys())[:5]
                status = f"OK - keys: {keys}"
            elif isinstance(data, list):
                status = f"OK - list with {len(data)} items"
        except Exception as e:
            status = f"FAILED - {type(e).__name__}"

        print(f"  {endpoint}: {status}")


async def main() -> None:
    """Main test function."""
    print("\n" + "=" * 60)
    print("  LOJACK API COMPREHENSIVE TEST")
    print("=" * 60)

    # Get credentials
    username = os.environ.get("LOJACK_USERNAME")
    password = os.environ.get("LOJACK_PASSWORD")

    if len(sys.argv) >= 3:
        username = sys.argv[1]
        password = sys.argv[2]

    if not username or not password:
        print("\nUsage:")
        print("  python examples/test_api.py <username> <password>")
        print("\nOr set environment variables:")
        print("  export LOJACK_USERNAME=your_username")
        print("  export LOJACK_PASSWORD=your_password")
        print("  python examples/test_api.py")
        sys.exit(1)

    # Test authentication
    client = await test_authentication(username, password)
    if not client:
        sys.exit(1)

    try:
        # Discover available endpoints
        await test_available_endpoints(client)

        # List devices
        devices = await test_list_devices(client)

        # Test locations for each device
        for device in devices:
            await test_device_locations(client, device)

        print_separator("TEST COMPLETE")
        print("\nIf locations are missing, check:")
        print("  1. Raw API responses above for location data")
        print("  2. Which endpoint returns location data")
        print("  3. The structure of the location data")
        print("\nThe raw responses will help identify the correct")
        print("endpoint and data format for your account.")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
