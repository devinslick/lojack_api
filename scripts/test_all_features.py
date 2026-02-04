"""Functional test script for all LoJack API features.

This script exercises all API functionality against a live account:
- Device listing and location
- Geofence CRUD operations
- Asset updates
- Maintenance schedules
- Repair orders
- User info and accounts

Usage:
    python test_all_features.py              # Run all tests
    python test_all_features.py --verbose    # Show detailed output
    python test_all_features.py --dry-run    # Skip write operations

Note: Create scripts/.credentials with username/password to authenticate.
"""

import argparse
import asyncio
from pathlib import Path

from lojack_api import LoJackClient, Vehicle


def load_credentials(path: Path) -> tuple[str | None, str | None]:
    """Load credentials from file."""
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


class FeatureTester:
    """Test all API features."""

    def __init__(self, client: LoJackClient, verbose: bool = False, dry_run: bool = False):
        self.client = client
        self.verbose = verbose
        self.dry_run = dry_run
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def log(self, msg: str, indent: int = 0):
        """Print a message with indentation."""
        prefix = "  " * indent
        print(f"{prefix}{msg}")

    def result(self, name: str, success: bool, details: str = ""):
        """Record and display a test result."""
        if success:
            self.passed += 1
            status = "[PASS]"
        else:
            self.failed += 1
            status = "[FAIL]"

        suffix = f" - {details}" if details else ""
        self.log(f"{status} {name}{suffix}", indent=1)

    def skip(self, name: str, reason: str = ""):
        """Record a skipped test."""
        self.skipped += 1
        suffix = f" - {reason}" if reason else ""
        self.log(f"[SKIP] {name}{suffix}", indent=1)

    async def test_list_devices(self) -> list:
        """Test listing devices."""
        self.log("\n--- Device Listing ---")
        try:
            devices = await self.client.list_devices()
            self.result("list_devices", True, f"Found {len(devices)} device(s)")

            for device in devices:
                device_type = "Vehicle" if isinstance(device, Vehicle) else "Device"
                self.log(f"  {device_type}: {device.name} ({device.id})", indent=1)
                if isinstance(device, Vehicle) and device.vin:
                    self.log(f"    VIN: {device.vin}", indent=1)

            return devices
        except Exception as e:
            self.result("list_devices", False, str(e))
            return []

    async def test_device_location(self, device) -> bool:
        """Test getting device location."""
        self.log(f"\n--- Location for {device.name} ---")
        try:
            location = await device.get_location(force=True)
            if location and location.latitude:
                self.result(
                    "get_location",
                    True,
                    f"{location.latitude:.6f}, {location.longitude:.6f}"
                )
                if self.verbose and location.timestamp:
                    self.log(f"    Timestamp: {location.timestamp.isoformat()}", indent=1)
                    if location.speed is not None:
                        self.log(f"    Speed: {location.speed}", indent=1)
                    if location.battery_voltage is not None:
                        self.log(f"    Battery: {location.battery_voltage}V", indent=1)
                return True
            else:
                self.result("get_location", False, "No location data")
                return False
        except Exception as e:
            self.result("get_location", False, str(e))
            return False

    async def test_location_history(self, device) -> bool:
        """Test getting location history."""
        try:
            count = 0
            async for _ in device.get_history(limit=5):
                count += 1
            self.result("get_history", True, f"{count} events")
            return True
        except Exception as e:
            self.result("get_history", False, str(e))
            return False

    async def test_geofences(self, device) -> bool:
        """Test geofence CRUD operations."""
        self.log(f"\n--- Geofences for {device.name} ---")

        # List geofences
        try:
            geofences = await device.list_geofences()
            self.result("list_geofences", True, f"Found {len(geofences)} geofence(s)")

            for gf in geofences:
                if self.verbose:
                    self.log(f"    {gf.name}: {gf.latitude}, {gf.longitude} (r={gf.radius}m)", indent=1)
        except Exception as e:
            self.result("list_geofences", False, str(e))
            return False

        # Create geofence (if not dry-run)
        if self.dry_run:
            self.skip("create_geofence", "dry-run mode")
            self.skip("update_geofence", "dry-run mode")
            self.skip("delete_geofence", "dry-run mode")
            return True

        test_geofence = None
        try:
            test_geofence = await device.create_geofence(
                name="API Test Geofence",
                latitude=32.8427,
                longitude=-97.0715,
                radius=50.0,
                address="Test Location"
            )
            if test_geofence and test_geofence.id:
                self.result("create_geofence", True, f"ID: {test_geofence.id}")
            else:
                self.result("create_geofence", False, "No geofence returned")
                return False
        except Exception as e:
            self.result("create_geofence", False, str(e))
            return False

        # Update geofence
        try:
            success = await device.update_geofence(
                test_geofence.id,
                name="API Test Geofence Updated",
                radius=75.0
            )
            self.result("update_geofence", success)
        except Exception as e:
            self.result("update_geofence", False, str(e))

        # Delete geofence
        try:
            success = await device.delete_geofence(test_geofence.id)
            self.result("delete_geofence", success)
        except Exception as e:
            self.result("delete_geofence", False, str(e))

        return True

    async def test_asset_update(self, device) -> bool:
        """Test updating asset information (read-only check)."""
        self.log(f"\n--- Asset Update for {device.name} ---")

        if self.dry_run:
            self.skip("update_asset", "dry-run mode")
            return True

        # We'll just verify the method doesn't error - we won't actually change anything
        # by passing no update parameters
        try:
            success = await device.update()  # No params = no actual change
            self.result("update_asset (no-op)", success)
            return True
        except Exception as e:
            self.result("update_asset", False, str(e))
            return False

    async def test_maintenance_schedule(self, vehicle: Vehicle) -> bool:
        """Test getting maintenance schedule."""
        self.log(f"\n--- Maintenance Schedule for {vehicle.name} ---")

        if not vehicle.vin:
            self.skip("get_maintenance_schedule", "No VIN available")
            return True

        try:
            schedule = await vehicle.get_maintenance_schedule()
            if schedule:
                self.result(
                    "get_maintenance_schedule",
                    True,
                    f"{len(schedule.items)} item(s)"
                )
                if self.verbose:
                    for item in schedule.items[:3]:  # Show first 3
                        self.log(f"    {item.name}: {item.severity}", indent=1)
            else:
                self.result("get_maintenance_schedule", True, "No schedule data")
            return True
        except Exception as e:
            self.result("get_maintenance_schedule", False, str(e))
            return False

    async def test_repair_orders(self, vehicle: Vehicle) -> bool:
        """Test getting repair orders."""
        self.log(f"\n--- Repair Orders for {vehicle.name} ---")

        try:
            orders = await vehicle.get_repair_orders()
            self.result("get_repair_orders", True, f"{len(orders)} order(s)")

            if self.verbose:
                for order in orders[:3]:  # Show first 3
                    status = order.status or "Unknown"
                    desc = order.description or "No description"
                    self.log(f"    [{status}] {desc[:40]}", indent=1)
            return True
        except Exception as e:
            self.result("get_repair_orders", False, str(e))
            return False

    async def test_user_info(self) -> bool:
        """Test getting user information."""
        self.log("\n--- User Information ---")

        try:
            user_info = await self.client.get_user_info()
            if user_info:
                self.result("get_user_info", True)
                if self.verbose:
                    for key in ("id", "email", "name", "username"):
                        if key in user_info:
                            self.log(f"    {key}: {user_info[key]}", indent=1)
            else:
                self.result("get_user_info", True, "No user info available")
            return True
        except Exception as e:
            self.result("get_user_info", False, str(e))
            return False

    async def test_accounts(self) -> bool:
        """Test getting accounts."""
        try:
            accounts = await self.client.get_accounts()
            self.result("get_accounts", True, f"{len(accounts)} account(s)")
            return True
        except Exception as e:
            self.result("get_accounts", False, str(e))
            return False

    async def run_all_tests(self):
        """Run all feature tests."""
        print("=" * 60)
        print("LoJack API Feature Tests")
        print("=" * 60)

        if self.dry_run:
            print("(Running in dry-run mode - write operations skipped)")

        # Test device listing
        devices = await self.test_list_devices()

        if not devices:
            print("\nNo devices found - cannot run device-specific tests")
            return

        # Test user/account info
        await self.test_user_info()
        await self.test_accounts()

        # Test each device
        for device in devices:
            print(f"\n{'=' * 60}")
            print(f"Testing: {device.name} ({device.id})")
            print("=" * 60)

            await self.test_device_location(device)
            await self.test_location_history(device)
            await self.test_geofences(device)
            await self.test_asset_update(device)

            # Vehicle-specific tests
            if isinstance(device, Vehicle):
                await self.test_maintenance_schedule(device)
                await self.test_repair_orders(device)

        # Summary
        print("\n" + "=" * 60)
        print("Test Summary")
        print("=" * 60)
        print(f"  Passed:  {self.passed}")
        print(f"  Failed:  {self.failed}")
        print(f"  Skipped: {self.skipped}")
        print("=" * 60)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test all LoJack API features against a live account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_all_features.py              Run all tests
  python test_all_features.py --verbose    Show detailed output
  python test_all_features.py --dry-run    Skip write operations (create/update/delete)

Note:
  Create scripts/.credentials with your username and password:
    username=your_email@example.com
    password=your_password
        """
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed test output"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip write operations (create, update, delete)"
    )

    args = parser.parse_args()

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
    try:
        client = await LoJackClient.create(username, password)
    except Exception as e:
        print(f"Authentication failed: {e}")
        return 1

    async with client:
        tester = FeatureTester(client, verbose=args.verbose, dry_run=args.dry_run)
        await tester.run_all_tests()

        return 0 if tester.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
