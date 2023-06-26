import pytest
import httpx
from pytapo import ClientInterface
from pytapo.error import AuthInvalidException, ResponseException


@pytest.fixture
def client():
    return ClientInterface("localhost", "admin", "password")


def test_init(client):
    assert client.host == "localhost"
    assert client.user == "admin"
    assert client.password == "password"


@pytest.mark.asyncio
async def test_refresh_stok_invalid_credentials():
    client = ClientInterface(
        "localhost", "admin", "password", perform_request=respond_invalid_auth
    )
    with pytest.raises(AuthInvalidException):
        await client.refreshStok()


@pytest.mark.asyncio
async def test_refresh_stok_valid_credentials():
    client = ClientInterface(
        "localhost", "admin", "password", perform_request=respond_valid_auth
    )
    assert await client.refreshStok() == "valid_stok"


@pytest.mark.asyncio
async def test_get_user_id():
    client = ClientInterface(
        "localhost",
        "admin",
        "password",
        perform_request=respond_get_user_id,
    )
    client.perform_request = respond_get_user_id
    assert await client.getUserID() == "valid_user_id"


async def respond_get_user_id(url, data, headers):
    return httpx.Response(
        200, json={"result": {"responses": [{"result": {"user_id": "valid_user_id"}}]}}
    )


async def respond_invalid_auth(url, data, headers):
    return httpx.Response(401, json={"result": {"data": {"code": -40411}}})


async def respond_valid_auth(url, data, headers):
    return httpx.Response(200, json={"result": {"stok": "valid_stok"}})


async def respond_get_user_id(url, data, headers):
    return httpx.Response(
        200, json={"result": {"responses": [{"result": {"user_id": "valid_user_id"}}]}}
    )
