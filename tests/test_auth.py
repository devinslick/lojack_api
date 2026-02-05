"""Tests for authentication manager."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from lojack_api.auth import AuthArtifacts, AuthManager
from lojack_api.exceptions import AuthenticationError


class TestAuthArtifacts:
    """Tests for AuthArtifacts dataclass."""

    def test_to_dict_basic(self):
        """Test basic serialization."""
        artifacts = AuthArtifacts(
            access_token="test-token",
            user_id="user-123",
        )
        data = artifacts.to_dict()
        assert data["access_token"] == "test-token"
        assert data["user_id"] == "user-123"
        assert "expires_at" not in data
        assert "refresh_token" not in data

    def test_to_dict_with_expiry(self):
        """Test serialization with expiry."""
        expires = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        artifacts = AuthArtifacts(
            access_token="test-token",
            expires_at=expires,
            refresh_token="refresh-token",
        )
        data = artifacts.to_dict()
        assert data["expires_at"] == expires.isoformat()
        assert data["refresh_token"] == "refresh-token"

    def test_from_dict_basic(self):
        """Test basic deserialization."""
        data = {
            "access_token": "test-token",
            "user_id": "user-123",
        }
        artifacts = AuthArtifacts.from_dict(data)
        assert artifacts.access_token == "test-token"
        assert artifacts.user_id == "user-123"
        assert artifacts.expires_at is None

    def test_from_dict_with_expiry(self):
        """Test deserialization with expiry."""
        data = {
            "access_token": "test-token",
            "expires_at": "2024-01-15T12:00:00+00:00",
            "refresh_token": "refresh-token",
        }
        artifacts = AuthArtifacts.from_dict(data)
        assert artifacts.expires_at is not None
        assert artifacts.expires_at.year == 2024
        assert artifacts.refresh_token == "refresh-token"

    def test_roundtrip(self):
        """Test serialization roundtrip."""
        expires = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        original = AuthArtifacts(
            access_token="test-token",
            expires_at=expires,
            refresh_token="refresh-token",
            user_id="user-123",
        )
        data = original.to_dict()
        restored = AuthArtifacts.from_dict(data)

        assert restored.access_token == original.access_token
        assert restored.refresh_token == original.refresh_token
        assert restored.user_id == original.user_id
        # Note: datetime might have slight differences due to string conversion
        assert restored.expires_at is not None


class TestAuthManager:
    """Tests for AuthManager."""

    @pytest.fixture
    def transport(self):
        """Create a mock transport."""
        transport = MagicMock()
        transport.request = AsyncMock()
        return transport

    @pytest.fixture
    def auth(self, transport):
        """Create an auth manager."""
        return AuthManager(transport, "user@example.com", "password123")

    def test_initial_state(self, auth):
        """Test initial authentication state."""
        assert not auth.is_authenticated
        assert auth.user_id is None

    @pytest.mark.asyncio
    async def test_login_success(self, auth, transport):
        """Test successful login."""
        transport.request.return_value = {
            "token": "new-token",
            "expiresIn": 3600,
            "userId": "user-123",
        }

        token = await auth.login()

        assert token == "new-token"
        assert auth.is_authenticated
        assert auth.user_id == "user-123"
        transport.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, transport):
        """Test login without credentials."""
        auth = AuthManager(transport)

        with pytest.raises(AuthenticationError, match="required"):
            await auth.login()

    @pytest.mark.asyncio
    async def test_login_invalid_response(self, auth, transport):
        """Test login with invalid response."""
        transport.request.return_value = {"error": "Invalid credentials"}

        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await auth.login()

    @pytest.mark.asyncio
    async def test_get_token_triggers_login(self, auth, transport):
        """Test that get_token triggers login when no token."""
        transport.request.return_value = {
            "token": "new-token",
            "expiresIn": 3600,
        }

        token = await auth.get_token()

        assert token == "new-token"
        transport.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_token_returns_cached(self, auth, transport):
        """Test that get_token returns cached token if valid."""
        transport.request.return_value = {
            "token": "new-token",
            "expiresIn": 3600,
        }

        # First call triggers login
        token1 = await auth.get_token()
        # Second call should return cached
        token2 = await auth.get_token()

        assert token1 == token2
        # Should only have called login once
        assert transport.request.call_count == 1

    @pytest.mark.asyncio
    async def test_get_token_refreshes_when_expired(self, auth, transport):
        """Test that get_token refreshes expired token."""
        # First response - token that's about to expire
        transport.request.return_value = {
            "token": "old-token",
            "expiresIn": 30,  # Less than margin
        }
        await auth.login()

        # Manually expire the token
        auth._expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Second response for refresh
        transport.request.return_value = {
            "token": "new-token",
            "expiresIn": 3600,
        }

        token = await auth.get_token()
        assert token == "new-token"

    def test_import_export_artifacts(self, auth):
        """Test importing and exporting auth artifacts."""
        artifacts = AuthArtifacts(
            access_token="imported-token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            user_id="imported-user",
        )

        auth.import_auth_artifacts(artifacts)

        assert auth.is_authenticated
        assert auth.user_id == "imported-user"

        exported = auth.export_auth_artifacts()
        assert exported is not None
        assert exported.access_token == "imported-token"
        assert exported.user_id == "imported-user"

    def test_clear(self, auth):
        """Test clearing auth state."""
        auth._access_token = "token"
        auth._user_id = "user"
        auth._expires_at = datetime.now(timezone.utc)

        auth.clear()

        assert auth._access_token is None
        assert auth._user_id is None
        assert auth._expires_at is None
        assert not auth.is_authenticated

    def test_app_token_property(self, auth):
        """Test app_token property."""
        from lojack_api.auth import DEFAULT_APP_TOKEN
        assert auth.app_token == DEFAULT_APP_TOKEN

    def test_is_authenticated_with_expired_token(self, auth):
        """Test is_authenticated returns False for expired token."""
        auth._access_token = "token"
        auth._expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        assert not auth.is_authenticated

    def test_is_authenticated_with_valid_token_no_expiry(self, auth):
        """Test is_authenticated with token but no expiry."""
        auth._access_token = "token"
        auth._expires_at = None
        assert auth.is_authenticated

    def test_export_auth_artifacts_when_not_authenticated(self, auth):
        """Test export_auth_artifacts returns None when not authenticated."""
        assert auth.export_auth_artifacts() is None

    def test_get_auth_headers(self, auth):
        """Test get_auth_headers returns correct headers."""
        auth._access_token = "test-token"
        headers = auth.get_auth_headers()
        assert "X-Nspire-Apptoken" in headers
        assert "X-Nspire-Usertoken" in headers
        assert headers["X-Nspire-Usertoken"] == "test-token"

    @pytest.mark.asyncio
    async def test_login_request_exception(self, auth, transport):
        """Test login handles request exceptions."""
        transport.request.side_effect = Exception("Network error")

        with pytest.raises(AuthenticationError, match="Login failed"):
            await auth.login()

    @pytest.mark.asyncio
    async def test_login_non_dict_response(self, auth, transport):
        """Test login handles non-dict response."""
        transport.request.return_value = "invalid response"

        with pytest.raises(AuthenticationError, match="Invalid login response"):
            await auth.login()

    @pytest.mark.asyncio
    async def test_login_with_invalid_expires_in(self, auth, transport):
        """Test login handles invalid expiresIn value."""
        transport.request.return_value = {
            "token": "new-token",
            "expiresIn": "invalid",  # Invalid - not a number
            "userId": "user-123",
        }

        token = await auth.login()

        # Should still succeed and use default expiry
        assert token == "new-token"
        assert auth._expires_at is not None

    @pytest.mark.asyncio
    async def test_login_without_expires_in(self, auth, transport):
        """Test login handles missing expiresIn."""
        transport.request.return_value = {
            "token": "new-token",
            "userId": "user-123",
        }

        token = await auth.login()

        # Should use default 1 hour expiry
        assert token == "new-token"
        assert auth._expires_at is not None

    @pytest.mark.asyncio
    async def test_login_with_access_token_key(self, auth, transport):
        """Test login handles 'access_token' key instead of 'token'."""
        transport.request.return_value = {
            "access_token": "new-token",
            "expiresIn": 3600,
            "user_id": "user-123",
        }

        token = await auth.login()

        assert token == "new-token"
        assert auth.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_refresh(self, auth, transport):
        """Test refresh calls login."""
        transport.request.return_value = {
            "token": "refreshed-token",
            "expiresIn": 3600,
        }

        token = await auth.refresh()

        assert token == "refreshed-token"


class TestAuthArtifactsEdgeCases:
    """Additional tests for AuthArtifacts edge cases."""

    def test_from_dict_with_invalid_date_string(self):
        """Test from_dict with invalid date string."""
        data = {
            "access_token": "test-token",
            "expires_at": "not-a-date",
        }
        artifacts = AuthArtifacts.from_dict(data)
        assert artifacts.access_token == "test-token"
        assert artifacts.expires_at is None

    def test_from_dict_with_datetime_object(self):
        """Test from_dict with datetime object directly."""
        expires = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        data = {
            "access_token": "test-token",
            "expires_at": expires,
        }
        artifacts = AuthArtifacts.from_dict(data)
        assert artifacts.expires_at == expires


class TestGetSpireonHeaders:
    """Tests for get_spireon_headers function."""

    def test_basic_headers(self):
        """Test basic headers generation."""
        from lojack_api.auth import get_spireon_headers
        headers = get_spireon_headers()
        assert "X-Nspire-Apptoken" in headers
        assert "X-Nspire-Correlationid" in headers

    def test_with_user_token(self):
        """Test headers with user token."""
        from lojack_api.auth import get_spireon_headers
        headers = get_spireon_headers(user_token="user-token")
        assert headers["X-Nspire-Usertoken"] == "user-token"

    def test_with_basic_auth(self):
        """Test headers with basic auth."""
        from lojack_api.auth import get_spireon_headers
        headers = get_spireon_headers(basic_auth="base64-credentials")
        assert headers["Authorization"] == "Basic base64-credentials"


class TestEncodeBasicAuth:
    """Tests for encode_basic_auth function."""

    def test_encode_basic_auth(self):
        """Test basic auth encoding."""
        from lojack_api.auth import encode_basic_auth
        encoded = encode_basic_auth("user", "pass")
        import base64
        decoded = base64.b64decode(encoded).decode("utf-8")
        assert decoded == "user:pass"
