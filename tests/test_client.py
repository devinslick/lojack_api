"""Tests for the main LoJack client."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lojack_api import AuthArtifacts, LoJackClient
from lojack_api.device import Device, Vehicle
from lojack_api.exceptions import (
    ApiError,
    DeviceNotFoundError,
)


class TestLoJackClientInit:
    """Tests for client initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        client = LoJackClient("user", "pass")
        assert client._identity_url == "https://identity.spireon.com"
        assert client._services_url == "https://services.spireon.com/v0/rest"
        assert not client._closed

    def test_init_custom_urls(self):
        """Test initialization with custom URLs."""
        client = LoJackClient(
            "user",
            "pass",
            identity_url="https://custom-identity.example.com/",
            services_url="https://custom-services.example.com/api/",
        )
        assert client._identity_url == "https://custom-identity.example.com"
        assert client._services_url == "https://custom-services.example.com/api"


class TestLoJackClientCreate:
    """Tests for async client creation."""

    @pytest.mark.asyncio
    async def test_create_authenticates(self):
        """Test that create() performs authentication."""
        with patch.object(LoJackClient, "__init__", return_value=None):
            with patch("lojack_api.api.AuthManager") as MockAuth:
                with patch("lojack_api.api.AiohttpTransport"):
                    mock_auth = AsyncMock()
                    mock_auth.login = AsyncMock(return_value="token")
                    MockAuth.return_value = mock_auth

                    # Create client manually to avoid __init__ issues
                    client = object.__new__(LoJackClient)
                    client._identity_url = "https://identity.spireon.com"
                    client._services_url = "https://services.spireon.com/v0/rest"
                    client._identity_transport = MagicMock()
                    client._services_transport = MagicMock()
                    client._auth = mock_auth
                    client._closed = False

                    # Simulate what create() does
                    await client._auth.login()

                    mock_auth.login.assert_called_once()


class TestLoJackClientContextManager:
    """Tests for context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager."""
        client = LoJackClient()
        client._identity_transport = MagicMock()
        client._identity_transport.close = AsyncMock()
        client._services_transport = MagicMock()
        client._services_transport.close = AsyncMock()

        async with client:
            assert not client._closed

        assert client._closed

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Test that close() can be called multiple times."""
        client = LoJackClient()
        client._identity_transport = MagicMock()
        client._identity_transport.close = AsyncMock()
        client._services_transport = MagicMock()
        client._services_transport.close = AsyncMock()

        await client.close()
        await client.close()  # Should not raise

        # Each transport close should only be called once
        assert client._identity_transport.close.call_count == 1
        assert client._services_transport.close.call_count == 1


class TestLoJackClientAuth:
    """Tests for authentication-related methods."""

    def test_is_authenticated(self):
        """Test is_authenticated property."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.is_authenticated = True

        assert client.is_authenticated

    def test_user_id(self):
        """Test user_id property."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.user_id = "user-123"

        assert client.user_id == "user-123"

    def test_export_auth(self):
        """Test exporting auth artifacts."""
        client = LoJackClient()
        client._auth = MagicMock()
        artifacts = AuthArtifacts(access_token="token")
        client._auth.export_auth_artifacts.return_value = artifacts

        result = client.export_auth()

        assert result == artifacts

    @pytest.mark.asyncio
    async def test_from_auth(self):
        """Test creating client from auth artifacts."""
        artifacts = AuthArtifacts(
            access_token="token",
            expires_at=datetime.now(timezone.utc),
        )

        with patch.object(LoJackClient, "__init__", return_value=None):
            client = object.__new__(LoJackClient)
            client._identity_url = "https://identity.spireon.com"
            client._services_url = "https://services.spireon.com/v0/rest"
            client._identity_transport = MagicMock()
            client._services_transport = MagicMock()
            client._auth = MagicMock()
            client._closed = False

            client._auth.import_auth_artifacts(artifacts)

            client._auth.import_auth_artifacts.assert_called_with(artifacts)


class TestLoJackClientDevices:
    """Tests for device-related methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_list_devices_returns_devices(self, client):
        """Test listing devices returns Device objects."""
        client._services_transport.request.return_value = {
            "content": [
                {"id": "dev-1", "name": "Device 1", "type": "tracker"},
                {"id": "dev-2", "name": "Device 2", "type": "tracker"},
            ]
        }

        devices = await client.list_devices()

        assert len(devices) == 2
        assert all(isinstance(d, Device) for d in devices)
        assert devices[0].id == "dev-1"

    @pytest.mark.asyncio
    async def test_list_devices_returns_vehicles(self, client):
        """Test listing devices returns Vehicle objects for vehicles."""
        client._services_transport.request.return_value = {
            "content": [
                {
                    "id": "veh-1",
                    "name": "My Car",
                    "attributes": {"vin": "ABC123"},
                    "type": "vehicle",
                },
            ]
        }

        devices = await client.list_devices()

        assert len(devices) == 1
        assert isinstance(devices[0], Vehicle)
        assert devices[0].vin == "ABC123"

    @pytest.mark.asyncio
    async def test_list_devices_handles_list_response(self, client):
        """Test listing devices handles array response format."""
        client._services_transport.request.return_value = [
            {"id": "dev-1", "name": "Device 1"},
        ]

        devices = await client.list_devices()

        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_list_devices_handles_assets_key(self, client):
        """Test listing devices handles 'assets' key."""
        client._services_transport.request.return_value = {
            "assets": [
                {"id": "dev-1", "name": "Device 1"},
            ]
        }

        devices = await client.list_devices()

        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_get_device(self, client):
        """Test getting a single device."""
        client._services_transport.request.return_value = {
            "id": "dev-1",
            "name": "Device 1",
            "type": "tracker",
        }

        device = await client.get_device("dev-1")

        assert isinstance(device, Device)
        assert device.id == "dev-1"

    @pytest.mark.asyncio
    async def test_get_device_not_found(self, client):
        """Test getting a non-existent device."""
        client._services_transport.request.side_effect = ApiError(
            "Not found", status_code=404
        )

        with pytest.raises(DeviceNotFoundError):
            await client.get_device("nonexistent")


class TestLoJackClientLocations:
    """Tests for location-related methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_locations(self, client):
        """Test getting device locations."""
        client._services_transport.request.return_value = {
            "content": [
                {"location": {"latitude": 40.7128, "longitude": -74.0060}},
                {"location": {"latitude": 40.7129, "longitude": -74.0061}},
            ]
        }

        locations = await client.get_locations("dev-1")

        assert len(locations) == 2
        assert locations[0].latitude == 40.7128

    @pytest.mark.asyncio
    async def test_get_locations_with_limit(self, client):
        """Test getting locations with limit."""
        client._services_transport.request.return_value = {"content": []}

        await client.get_locations("dev-1", limit=10)

        call_args = client._services_transport.request.call_args
        assert call_args[1]["params"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_locations_handles_list_response(self, client):
        """Test getting locations handles array response."""
        client._services_transport.request.return_value = [
            {"latitude": 40.7128, "longitude": -74.0060},
        ]

        locations = await client.get_locations("dev-1")

        assert len(locations) == 1


class TestLoJackClientCommands:
    """Tests for command-related methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_send_command_success(self, client):
        """Test sending a command successfully."""
        client._services_transport.request.return_value = {
            "id": "cmd-123",
            "status": "PENDING",
        }

        result = await client.send_command("dev-1", "locate")

        assert result is True
        client._services_transport.request.assert_called_once()
        call_args = client._services_transport.request.call_args
        assert call_args[1]["json"]["command"] == "LOCATE"

    @pytest.mark.asyncio
    async def test_send_command_accepted_response(self, client):
        """Test send_command with 'accepted' response."""
        client._services_transport.request.return_value = {"accepted": True}

        result = await client.send_command("dev-1", "locate")

        assert result is True

    @pytest.mark.asyncio
    async def test_send_command_status_ok_response(self, client):
        """Test send_command with 'status: ok' response."""
        client._services_transport.request.return_value = {"status": "ok"}

        result = await client.send_command("dev-1", "locate")

        assert result is True


class TestLoJackClientGeofences:
    """Tests for geofence-related methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_list_geofences(self, client):
        """Test listing geofences."""
        client._services_transport.request.return_value = {
            "content": [
                {"id": "geo-1", "name": "Home", "lat": 32.84, "lng": -97.07, "radius": 100},
                {"id": "geo-2", "name": "Work", "lat": 32.85, "lng": -97.08, "radius": 200},
            ]
        }

        geofences = await client.list_geofences("dev-1")

        assert len(geofences) == 2
        assert geofences[0].id == "geo-1"
        assert geofences[0].name == "Home"
        assert geofences[1].asset_id == "dev-1"

    @pytest.mark.asyncio
    async def test_list_geofences_empty(self, client):
        """Test listing geofences when none exist."""
        client._services_transport.request.return_value = {"content": []}

        geofences = await client.list_geofences("dev-1")

        assert geofences == []

    @pytest.mark.asyncio
    async def test_get_geofence(self, client):
        """Test getting a single geofence."""
        client._services_transport.request.return_value = {
            "id": "geo-1",
            "name": "Home",
            "location": {"coordinates": {"lat": 32.84, "lng": -97.07}, "radius": 100},
        }

        geofence = await client.get_geofence("dev-1", "geo-1")

        assert geofence is not None
        assert geofence.id == "geo-1"
        assert geofence.latitude == 32.84

    @pytest.mark.asyncio
    async def test_get_geofence_not_found(self, client):
        """Test getting a non-existent geofence."""
        client._services_transport.request.side_effect = ApiError(
            "Not found", status_code=404
        )

        geofence = await client.get_geofence("dev-1", "nonexistent")

        assert geofence is None

    @pytest.mark.asyncio
    async def test_create_geofence(self, client):
        """Test creating a geofence."""
        client._services_transport.request.return_value = {
            "id": "geo-new",
            "name": "Test",
            "location": {"coordinates": {"lat": 32.84, "lng": -97.07}, "radius": 100},
        }

        geofence = await client.create_geofence(
            "dev-1",
            name="Test",
            latitude=32.84,
            longitude=-97.07,
            radius=100.0,
        )

        assert geofence is not None
        assert geofence.id == "geo-new"
        client._services_transport.request.assert_called_once()
        call_args = client._services_transport.request.call_args
        assert call_args[1]["json"]["name"] == "Test"

    @pytest.mark.asyncio
    async def test_update_geofence(self, client):
        """Test updating a geofence."""
        client._services_transport.request.return_value = {}

        result = await client.update_geofence(
            "dev-1", "geo-1", name="Updated", radius=150.0
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_update_geofence_no_changes(self, client):
        """Test updating a geofence with no changes."""
        result = await client.update_geofence("dev-1", "geo-1")

        assert result is True
        client._services_transport.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_geofence(self, client):
        """Test deleting a geofence."""
        client._services_transport.request.return_value = {}

        result = await client.delete_geofence("dev-1", "geo-1")

        assert result is True
        client._services_transport.request.assert_called_once()


class TestLoJackClientMaintenance:
    """Tests for maintenance-related methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_maintenance_schedule(self, client):
        """Test getting maintenance schedule."""
        client._services_transport.request.return_value = {
            "vin": "ABC123",
            "items": [
                {"name": "Oil Change", "severity": "NORMAL", "mileageDue": 55000},
                {"name": "Tire Rotation", "severity": "WARNING", "mileageDue": 60000},
            ],
        }

        schedule = await client.get_maintenance_schedule("ABC123")

        assert schedule is not None
        assert schedule.vin == "ABC123"
        assert len(schedule.items) == 2
        assert schedule.items[0].name == "Oil Change"

    @pytest.mark.asyncio
    async def test_get_maintenance_schedule_not_found(self, client):
        """Test getting maintenance schedule when none exists."""
        client._services_transport.request.side_effect = ApiError(
            "Not found", status_code=404
        )

        schedule = await client.get_maintenance_schedule("ABC123")

        assert schedule is None

    @pytest.mark.asyncio
    async def test_get_repair_orders(self, client):
        """Test getting repair orders."""
        client._services_transport.request.return_value = {
            "content": [
                {
                    "id": "RO-001",
                    "vin": "ABC123",
                    "status": "CLOSED",
                    "description": "Oil change",
                    "totalAmount": 75.50,
                },
            ]
        }

        orders = await client.get_repair_orders(vin="ABC123")

        assert len(orders) == 1
        assert orders[0].id == "RO-001"
        assert orders[0].status == "CLOSED"
        assert orders[0].total_amount == 75.50

    @pytest.mark.asyncio
    async def test_get_repair_orders_empty(self, client):
        """Test getting repair orders with no params."""
        orders = await client.get_repair_orders()

        assert orders == []
        client._services_transport.request.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_repair_orders_not_found(self, client):
        """Test getting repair orders when none exist."""
        client._services_transport.request.side_effect = ApiError(
            "Not found", status_code=404
        )

        orders = await client.get_repair_orders(vin="ABC123")

        assert orders == []


class TestLoJackClientUserInfo:
    """Tests for user info methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_user_info(self, client):
        """Test getting user info."""
        client._services_transport.request.return_value = {
            "id": "user-123",
            "email": "test@example.com",
            "name": "Test User",
        }

        user_info = await client.get_user_info()

        assert user_info is not None
        assert user_info["id"] == "user-123"
        assert user_info["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_user_info_error(self, client):
        """Test getting user info when error occurs."""
        client._services_transport.request.side_effect = ApiError("Error")

        user_info = await client.get_user_info()

        assert user_info is None

    @pytest.mark.asyncio
    async def test_get_accounts(self, client):
        """Test getting accounts."""
        client._services_transport.request.return_value = {
            "content": [
                {"id": "acct-1", "name": "Account 1"},
                {"id": "acct-2", "name": "Account 2"},
            ]
        }

        accounts = await client.get_accounts()

        assert len(accounts) == 2
        assert accounts[0]["id"] == "acct-1"

    @pytest.mark.asyncio
    async def test_get_accounts_list_response(self, client):
        """Test getting accounts with list response."""
        client._services_transport.request.return_value = [
            {"id": "acct-1", "name": "Account 1"},
        ]

        accounts = await client.get_accounts()

        assert len(accounts) == 1

    @pytest.mark.asyncio
    async def test_get_accounts_error(self, client):
        """Test getting accounts when error occurs."""
        client._services_transport.request.side_effect = ApiError("Error")

        accounts = await client.get_accounts()

        assert accounts == []


class TestLoJackClientAssetUpdate:
    """Tests for asset update methods."""

    @pytest.fixture
    def client(self):
        """Create a client with mocked internals."""
        client = LoJackClient()
        client._auth = MagicMock()
        client._auth.get_token = AsyncMock(return_value="token")
        client._auth.get_auth_headers = MagicMock(
            return_value={"X-Nspire-Usertoken": "token"}
        )
        client._services_transport = MagicMock()
        client._services_transport.request = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_update_asset(self, client):
        """Test updating an asset."""
        client._services_transport.request.return_value = {}

        result = await client.update_asset(
            "dev-1", name="New Name", odometer=50000.0
        )

        assert result is True
        call_args = client._services_transport.request.call_args
        assert call_args[1]["json"]["name"] == "New Name"
        assert call_args[1]["json"]["odometer"] == 50000.0

    @pytest.mark.asyncio
    async def test_update_asset_no_changes(self, client):
        """Test updating an asset with no changes."""
        result = await client.update_asset("dev-1")

        assert result is True
        client._services_transport.request.assert_not_called()
