from datetime import datetime
from functools import wraps
import hashlib
import httpx
import json
from rich import print as rprint

from pytapo.error import AuthInvalidException, ResponseException


def ensure_authenticated(method):
    """
    A decorator to ensure that the client is authenticated before executing any function.
    """

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if not self.stok:
            self.refreshStok()
        return method(self, *args, **kwargs)

    return wrapper


class ClientInterface:
    """
    A ClientInterface for communicating with Tapo Camera
    """

    def __init__(
        self,
        host,
        user,
        password,
        cloudPassword="",
        superSecretKey="",
        perform_request=None,
        execute_function=None,
        childID=None,
    ):
        """
        Initialize the client interface with the host, user and password.
        Optionally also specify cloudPassword, superSecretKey and childID.
        """
        self.host = host
        self.user = user
        self.password = password
        self.cloudPassword = cloudPassword
        self.superSecretKey = superSecretKey
        self.stok = False
        self.userID = False
        self.childID = childID
        self.headers = {
            "Host": self.host,
            "Referer": "https://{host}".format(host=self.host),
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Tapo CameraClient Android",
            "Connection": "close",
            "requestByApp": "true",
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.hashedPassword = hashlib.md5(password.encode("utf8")).hexdigest().upper()
        self.hashedCloudPassword = (
            hashlib.md5(cloudPassword.encode("utf8")).hexdigest().upper()
        )
        self.perform_request = perform_request or self._perform_request
        self.execute_function = execute_function or self._execute_function

    async def _perform_request(self, url, data, headers):
        async with httpx.AsyncClient() as client:
            return await client.post(url, data=json.dumps(data), headers=headers)

    async def _execute_function(self, url, data, headers):
        return await httpx.post(url, data=json.dumps(data), headers=headers)

    def ensureAuthenticated(self):
        """
        Ensure the client is authenticated.
        If not already authenticated, it triggers refreshStok to fetch a new token.
        """
        return True if self.stok else self.refreshStok()

    async def refreshStok(self):
        """
        Authenticate and refresh the token.
        Raise AuthInvalidException for invalid username or password.
        """
        url = f"https://{self.host}"
        data = {
            "method": "login",
            "params": {
                "hashed": True,
                "password": self.hashedPassword,
                "username": self.user,
            },
        }
        async with httpx.AsyncClient() as client:
            res = await self.perform_request(url, data, self.headers)
        if res.status_code == 401:
            data = res.json()
            if data["result"]["data"]["code"] == -40411:
                raise AuthInvalidException("Invalid username or password")
        if self.responseIsOK(res):
            self.stok = res.json()["result"]["stok"]
            return self.stok
        raise AuthInvalidException("Invalid username or password")

    def responseIsOK(self, res):
        """
        Check if the response is OK.
        Raise ResponseException for any errors.
        """
        if res.status_code != 200:
            raise ResponseException(
                f"Error communicating with Tapo Camera. Status code: {str(res.status_code)}"
            )
        data = res.json()
        if "error_code" not in data or data["error_code"] == 0:
            return True
        raise ResponseException(
            f"Error communicating with Tapo Camera. Error code: {str(data['error_code'])}"
        )

    @ensure_authenticated
    async def getUserID(self):
        """
        Get the userID.
        If userID is not already fetched, it triggers a request to fetch the userID.
        """
        url = f"https://{self.host}/stok={self.stok}/ds"
        data = {
            "method": "getUserID",
            "params": {"system": {"get_user_id": "null"}},
        }

        if not self.userID:
            res = await self.perform_request(url, data, self.headers)
        self.userID = res.json()["result"]["responses"][0]["result"]["user_id"]
        return self.userID
