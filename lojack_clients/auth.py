"""Authentication manager for LoJack API.

Handles token-based authentication with automatic refresh and
session resumption support for Home Assistant integrations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, Optional

from .exceptions import AuthenticationError

if TYPE_CHECKING:
    from .transport import AiohttpTransport


@dataclass
class AuthArtifacts:
    """Exported authentication state for session resumption.

    This allows Home Assistant to persist authentication across restarts
    without storing the raw password.
    """

    access_token: str
    expires_at: Optional[datetime] = None
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for JSON serialization."""
        data: Dict[str, Any] = {"access_token": self.access_token}
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        if self.refresh_token:
            data["refresh_token"] = self.refresh_token
        if self.user_id:
            data["user_id"] = self.user_id
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthArtifacts":
        """Create from a dictionary (e.g., loaded from JSON)."""
        expires_at = None
        if exp := data.get("expires_at"):
            if isinstance(exp, str):
                try:
                    expires_at = datetime.fromisoformat(exp)
                except ValueError:
                    pass
            elif isinstance(exp, datetime):
                expires_at = exp

        return cls(
            access_token=data["access_token"],
            expires_at=expires_at,
            refresh_token=data.get("refresh_token"),
            user_id=data.get("user_id"),
        )


class AuthManager:
    """Manages authentication tokens for the LoJack API.

    Features:
    - Automatic token refresh when expired
    - Session resumption via export/import of auth artifacts
    - Support for refresh tokens if the API provides them

    Args:
        transport: The HTTP transport to use for auth requests.
        username: LoJack account username/email.
        password: LoJack account password.
        token_refresh_margin: Seconds before expiry to trigger refresh (default: 60).
    """

    def __init__(
        self,
        transport: "AiohttpTransport",
        username: Optional[str] = None,
        password: Optional[str] = None,
        token_refresh_margin: int = 60,
    ) -> None:
        self._transport = transport
        self._username = username
        self._password = password
        self._token_refresh_margin = token_refresh_margin

        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._user_id: Optional[str] = None

    @property
    def is_authenticated(self) -> bool:
        """Return True if we have a valid (non-expired) token."""
        if not self._access_token:
            return False
        if self._expires_at:
            return datetime.now(timezone.utc) < self._expires_at
        return True

    @property
    def user_id(self) -> Optional[str]:
        """Return the authenticated user ID if available."""
        return self._user_id

    def import_auth_artifacts(self, artifacts: AuthArtifacts) -> None:
        """Import previously exported auth state for session resumption.

        Args:
            artifacts: Authentication artifacts from a previous session.
        """
        self._access_token = artifacts.access_token
        self._expires_at = artifacts.expires_at
        self._refresh_token = artifacts.refresh_token
        self._user_id = artifacts.user_id

    def export_auth_artifacts(self) -> Optional[AuthArtifacts]:
        """Export current auth state for persistence.

        Returns:
            AuthArtifacts if authenticated, None otherwise.
        """
        if not self._access_token:
            return None

        return AuthArtifacts(
            access_token=self._access_token,
            expires_at=self._expires_at,
            refresh_token=self._refresh_token,
            user_id=self._user_id,
        )

    async def login(self) -> str:
        """Authenticate with the API using username/password.

        Returns:
            The access token.

        Raises:
            AuthenticationError: If credentials are missing or login fails.
        """
        if not self._username or not self._password:
            raise AuthenticationError("Username and password are required for login")

        payload = {
            "username": self._username,
            "password": self._password,
        }

        try:
            data = await self._transport.request("POST", "/auth/login", json=payload)
        except Exception as e:
            raise AuthenticationError(f"Login failed: {e}") from e

        if not isinstance(data, dict):
            raise AuthenticationError("Invalid login response")

        token_value = data.get("access_token") or data.get("token")
        if not token_value:
            error = data.get("error") or data.get("message") or "No token in response"
            raise AuthenticationError(f"Login failed: {error}")

        token: str = str(token_value)
        self._access_token = token
        self._refresh_token = data.get("refresh_token")
        self._user_id = data.get("user_id") or data.get("userId")

        # Parse expiration
        expires_in = data.get("expires_in") or data.get("expiresIn")
        if expires_in:
            try:
                self._expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(expires_in)
                )
            except (ValueError, TypeError):
                self._expires_at = None
        else:
            # Check for explicit expiration timestamp
            expires_at = data.get("expires_at") or data.get("expiresAt")
            if expires_at:
                if isinstance(expires_at, (int, float)):
                    self._expires_at = datetime.fromtimestamp(
                        expires_at, tz=timezone.utc
                    )
                elif isinstance(expires_at, str):
                    try:
                        self._expires_at = datetime.fromisoformat(
                            expires_at.replace("Z", "+00:00")
                        )
                    except ValueError:
                        self._expires_at = None

        return token

    async def refresh(self) -> str:
        """Refresh the access token using the refresh token.

        Falls back to re-login if no refresh token is available.

        Returns:
            The new access token.

        Raises:
            AuthenticationError: If refresh fails.
        """
        if not self._refresh_token:
            # No refresh token, try re-login
            return await self.login()

        payload = {"refresh_token": self._refresh_token}

        try:
            data = await self._transport.request("POST", "/auth/refresh", json=payload)
        except AuthenticationError:
            # Refresh token might be invalid, try re-login
            return await self.login()
        except Exception as e:
            raise AuthenticationError(f"Token refresh failed: {e}") from e

        if not isinstance(data, dict):
            return await self.login()

        token_value = data.get("access_token") or data.get("token")
        if not token_value:
            return await self.login()

        token: str = str(token_value)
        self._access_token = token
        if new_refresh := data.get("refresh_token"):
            self._refresh_token = str(new_refresh)

        expires_in = data.get("expires_in") or data.get("expiresIn")
        if expires_in:
            try:
                self._expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(expires_in)
                )
            except (ValueError, TypeError):
                pass

        return token

    async def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary.

        Returns:
            A valid access token.

        Raises:
            AuthenticationError: If unable to get a valid token.
        """
        if not self._access_token:
            return await self.login()

        # Check if token is expired or about to expire
        if self._expires_at:
            margin = timedelta(seconds=self._token_refresh_margin)
            if datetime.now(timezone.utc) >= (self._expires_at - margin):
                return await self.refresh()

        return self._access_token

    def clear(self) -> None:
        """Clear all authentication state."""
        self._access_token = None
        self._refresh_token = None
        self._expires_at = None
        self._user_id = None
