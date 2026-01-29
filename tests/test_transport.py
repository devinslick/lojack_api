import pytest

from lojack_clients.transport import AiohttpClient


@pytest.mark.asyncio
async def test_session_create_close():
    client = AiohttpClient("http://example.com", timeout=1)
    # create session
    session = await client._get_session()
    assert session is not None
    await client.close()
    assert client._session is None
