from unittest.mock import AsyncMock
from httpx import AsyncClient
import pytest
from pytapo import Tapo
from pytapo.error import ResponseException
from types import SimpleNamespace


@pytest.fixture
async def client():
    return AsyncClient()


@pytest.fixture
def tapo():
    tapo = Tapo("localhost", "user", "password")
    tapo.stok = "dummy_stok"
    return tapo


@pytest.mark.asyncio
async def test_performRequest_success(mocker, tapo):
    data = {"key": "value"}
    mocker.patch.object(tapo, "responseIsOK", return_value=True)

    # Mock the post method to return an object with a 'json' method
    post_return_value = SimpleNamespace(json=AsyncMock(return_value=data))
    mocker.patch.object(AsyncClient, "post", new_callable=AsyncMock, return_value=post_return_value)

    mocker.patch.object(
        tapo, "getHostURL", return_value="https://localhost/stok=dummy_stok/ds"
    )
    response = await tapo.performRequest(data)
    assert await response == data  # await here


@pytest.mark.asyncio
async def test_performRequest_fail(mocker, tapo):
    data = {"error_code": -40401}
    mocker.patch.object(tapo, "responseIsOK", return_value=False)

    # Mock the post method to return an object with a 'json' method
    post_return_value = SimpleNamespace(json=AsyncMock(return_value=data))
    mocker.patch.object(AsyncClient, "post", new_callable=AsyncMock, return_value=post_return_value)

    mocker.patch.object(
        tapo, "getHostURL", return_value="https://localhost/stok=dummy_stok/ds"
    )
    with pytest.raises(ResponseException):
        await tapo.performRequest(data)


@pytest.mark.asyncio
async def test_getHostURL(mocker, tapo):
    mocker.patch.object(tapo, "stok", "dummy_stok")
    assert tapo.getHostURL() == "https://localhost/stok=dummy_stok/ds"


@pytest.mark.asyncio
async def test_getStreamURL(tapo):
    assert tapo.getStreamURL() == "localhost:8800"
