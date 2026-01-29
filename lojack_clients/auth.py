import datetime
from typing import Optional

from .transport import AiohttpClient


class AuthManager:
    """Simple token manager that performs login and refresh when needed.

    This uses the transport to call an `/auth/login` endpoint returning
    an `access_token` and optional `expires_in` seconds.
    """
    def __init__(self, transport: AiohttpClient, username: str, password: str):
        self.transport = transport
        self.username = username
        self.password = password
        self._token: Optional[str] = None
        self._expires: Optional[datetime.datetime] = None

    async def login(self) -> Optional[str]:
        payload = {"username": self.username, "password": self.password}
        data = await self.transport.request("POST", "/auth/login", json=payload)
        token = data.get("access_token") if isinstance(data, dict) else None
        self._token = token
        expires_in = data.get("expires_in") if isinstance(data, dict) else None
        if expires_in:
            self._expires = datetime.datetime.utcnow() + datetime.timedelta(seconds=int(expires_in))
        return self._token

    async def get_token(self) -> Optional[str]:
        if not self._token or (self._expires and datetime.datetime.utcnow() >= self._expires):
            await self.login()
        return self._token
