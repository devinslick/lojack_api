"""Authentication manager for Spireon LoJack API.

Handles token-based authentication with automatic refresh and
session resumption support for Home Assistant integrations.

The Spireon LoJack API uses:
- Basic Auth for initial token retrieval from the identity service
- X-Nspire-Usertoken header for subsequent API calls
- X-Nspire-Apptoken and X-Nspire-Correlationid headers on all requests
"""

from __future__ import annotations

import base64
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .exceptions import AuthenticationError

if TYPE_CHECKING:
    from .transport import AiohttpTransport


# Default app token for LoJack (systemId=23, brandId=81)
DEFAULT_APP_TOKEN = "eyJzeXN0ZW1JZCI6MjMsImJyYW5kSWQiOjgxfQ=="


@dataclass
class AuthArtifacts:
    """Exported authentication state for session resumption.

    This allows Home Assistant to persist authentication across restarts
    without storing the raw password.
    """

    access_token: str
    expires_at: datetime | None = None
    refresh_token: str | None = None
    user_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a dictionary for JSON serialization."""
        data: dict[str, Any] = {"access_token": self.access_token}
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        if self.refresh_token:
            data["refresh_token"] = self.refresh_token
        if self.user_id:
            data["user_id"] = self.user_id
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AuthArtifacts:
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


def get_spireon_headers(
    app_token: str = DEFAULT_APP_TOKEN,
    user_token: str | None = None,
    basic_auth: str | None = None,
) -> dict[str, str]:
    """Build headers for Spireon API requests.

    Args:
        app_token: The X-Nspire-Apptoken value.
        user_token: Optional X-Nspire-Usertoken for authenticated requests.
        basic_auth: Optional Basic auth string for identity requests.

    Returns:
        Dictionary of headers to use in requests.
    """
    headers = {
        "X-Nspire-Apptoken": app_token,
        "X-Nspire-Correlationid": str(uuid.uuid4()),
    }
    if user_token:
        headers["X-Nspire-Usertoken"] = user_token
    if basic_auth:
        headers["Authorization"] = f"Basic {basic_auth}"
    return headers


def encode_basic_auth(username: str, password: str) -> str:
    """Encode username and password for Basic auth."""
    credentials = f"{username}:{password}"
    return base64.b64encode(credentials.encode("utf-8")).decode("ascii")


class AuthManager:
    """Manages authentication tokens for the Spireon LoJack API.

    Features:
    - Basic Auth for initial token retrieval
    - Automatic token refresh when expired (via re-login)
    - Session resumption via export/import of auth artifacts
    - Proper Spireon-specific headers

    Args:
        transport: The HTTP transport to use for auth requests.
        username: LoJack account username/email.
        password: LoJack account password.
        app_token: The X-Nspire-Apptoken value (default: LoJack app token).
        token_refresh_margin: Seconds before expiry to trigger refresh (default: 60).
    """

    def __init__(
        self,
        transport: AiohttpTransport,
        username: str | None = None,
        password: str | None = None,
        app_token: str = DEFAULT_APP_TOKEN,
        token_refresh_margin: int = 60,
    ) -> None:
        self._transport = transport
        self._username = username
        self._password = password
        self._app_token = app_token
        self._token_refresh_margin = token_refresh_margin

        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._user_id: str | None = None

    @property
    def is_authenticated(self) -> bool:
        """Return True if we have a valid (non-expired) token."""
        if not self._access_token:
            return False
        if self._expires_at:
            return datetime.now(timezone.utc) < self._expires_at
        return True

    @property
    def user_id(self) -> str | None:
        """Return the authenticated user ID if available."""
        return self._user_id

    @property
    def app_token(self) -> str:
        """Return the app token used for requests."""
        return self._app_token

    def import_auth_artifacts(self, artifacts: AuthArtifacts) -> None:
        """Import previously exported auth state for session resumption.

        Args:
            artifacts: Authentication artifacts from a previous session.
        """
        self._access_token = artifacts.access_token
        self._expires_at = artifacts.expires_at
        self._user_id = artifacts.user_id

    def export_auth_artifacts(self) -> AuthArtifacts | None:
        """Export current auth state for persistence.

        Returns:
            AuthArtifacts if authenticated, None otherwise.
        """
        if not self._access_token:
            return None

        return AuthArtifacts(
            access_token=self._access_token,
            expires_at=self._expires_at,
            user_id=self._user_id,
        )

    async def login(self) -> str:
        """Authenticate with the identity service using Basic Auth.

        Returns:
            The user token (X-Nspire-Usertoken).

        Raises:
            AuthenticationError: If credentials are missing or login fails.
        """
        if not self._username or not self._password:
            raise AuthenticationError("Username and password are required for login")

        basic_auth = encode_basic_auth(self._username, self._password)
        headers = get_spireon_headers(app_token=self._app_token, basic_auth=basic_auth)

        try:
            data = await self._transport.request(
                "GET", "/identity/token", headers=headers
            )
        except Exception as e:
            raise AuthenticationError(f"Login failed: {e}") from e

        if not isinstance(data, dict):
            raise AuthenticationError("Invalid login response")

        token_value = data.get("token") or data.get("access_token")
        if not token_value:
            error = data.get("error") or data.get("message") or "No token in response"
            raise AuthenticationError(f"Login failed: {error}")

        token: str = str(token_value)
        self._access_token = token
        self._user_id = data.get("userId") or data.get("user_id")

        # Parse expiration - tokens typically expire after some time
        expires_in = data.get("expiresIn") or data.get("expires_in")
        if expires_in:
            try:
                self._expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(expires_in)
                )
            except (ValueError, TypeError):
                # Default to 1 hour if not specified
                self._expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        else:
            # Default expiration if not provided
            self._expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        return token

    async def refresh(self) -> str:
        """Refresh the access token by re-logging in.

        The Spireon API doesn't have a separate refresh endpoint,
        so we re-authenticate with credentials.

        Returns:
            The new user token.

        Raises:
            AuthenticationError: If refresh fails.
        """
        return await self.login()

    async def get_token(self) -> str:
        """Get a valid access token, refreshing if necessary.

        Returns:
            A valid user token.

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

    def get_auth_headers(self) -> dict[str, str]:
        """Get headers for authenticated API requests.

        Returns:
            Headers dict with app token, correlation ID, and user token.
        """
        return get_spireon_headers(
            app_token=self._app_token,
            user_token=self._access_token,
        )

    def clear(self) -> None:
        """Clear all authentication state."""
        self._access_token = None
        self._expires_at = None
        self._user_id = None
