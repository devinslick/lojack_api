import aiohttp
from typing import Optional, Any, Dict

class AiohttpClient:
    """Simple HTTP transport using aiohttp.

    Keeps an optionally provided `aiohttp.ClientSession` or creates one lazily.
    """
    def __init__(self, base_url: str, session: Optional[aiohttp.ClientSession] = None, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def request(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None,
                      json: Optional[Any] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        session = await self._get_session()
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with session.request(method, url, params=params, json=json, headers=headers) as resp:
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return await resp.json()
            return await resp.text()

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
