from datetime import datetime
import hashlib
import json

from httpx import AsyncClient
from pytapo.client.client import ensure_authenticated
from pytapo.const import MAX_LOGIN_RETRIES
from pytapo.error import ResponseException
from pytapo.media_stream.session import HttpMediaSession
from pytapo.settings import (
    DeviceInterface,
    ImageInterface,
)
from pytapo.motor.presets import PresetInterface
from pytapo.recording.recording import RecordingInterface
from pytapo.motor.motor import MotorInterface

from pytapo.client.client import ClientInterface


class Tapo:
    """
    Tapo class is a wrapper over various services provided by Tapo Camera.
    """

    def __init__(
        self, host, user, password, cloudPassword="", superSecretKey="", childID=None
    ):
        """
        Initialize the Tapo instance with user credentials, host and optional settings.
        It initializes different interfaces such as device interface, preset interface etc.
        """
        self.host = host
        self.user = user
        self.password = password
        self.cloudPassword = cloudPassword
        self.superSecretKey = superSecretKey
        self.deviceInterface = DeviceInterface(self.performRequest, self.executeFunction, childID)
        self.presetInterface = PresetInterface(self.executeFunction)
        self.recordingInterface = RecordingInterface(self.performRequest, self.executeFunction, childID)
        self.imageInterface = ImageInterface(self.performRequest, self.executeFunction, childID)
        self.motorInterface = MotorInterface(self.performRequest, self.executeFunction, childID)
        self.client = ClientInterface(host, user, password, cloudPassword, superSecretKey, self.performRequest, self.executeFunction, childID)
        self.mediaSession = HttpMediaSession(host, cloudPassword, superSecretKey)

    def getBasicInfo(self):
        """
        Returns the basic information about the device.
        """
        return self.deviceInterface.getBasicInfo()

    def isSupported(self):
        """
        Returns True if the device is supported.
        """
        return self.presetInterface.isSupportingPresets() or {}

    def getMediaSession(self):
        """
        Returns the HttpMediaSession instance.
        """
        return HttpMediaSession(self.host, self.cloudPassword, self.superSecretKey)

    def getHostURL(self):
        """
        Returns the host URL with stok for further API calls.
        """
        return f"https://{self.host}/stok={self.stok}/ds"

    def getStreamURL(self):
        """
        Returns the Stream URL for video streaming.
        """
        return f"{self.host}:8800"

    def reboot(self):
        """
        Reboots the device.
        """
        return self.executeFunction("rebootDevice", {"system": {"reboot": "null"}})

    def executeFunction(self, method, params, retry=False):
        """
        Executes a method with given params. If the method is "multipleRequest", it performs the request for each param.
        In case of error, it retries the execution once.
        """
        if method == "multipleRequest":
            data = self.performRequest({"method": "multipleRequest", "params": params})[
                "result"
            ]["responses"]
        else:
            data = self.performRequest(
                {
                    "method": "multipleRequest",
                    "params": {"requests": [{"method": method, "params": params}]},
                }
            )["result"]["responses"][0]
        if isinstance(data, list):
            return data
        if "result" in data and ("error_code" not in data or data["error_code"] == 0):
            return data["result"]
        if "error_code" in data and data["error_code"] == -64303 and retry is False:
            self.setCruise(False)
            return self.executeFunction(method, params, True)
        raise ResponseException(
            f'Error: {data["err_msg"] if "err_msg" in data else self.getErrorMessage(data["error_code"])}, Response: {json.dumps(data)}'
        )

    @ensure_authenticated
    async def performRequest(self, requestData, loginRetryCount=0):
        """
        Performs a request with given data. In case of error, it retries the request up to MAX_LOGIN_RETRIES.
        """
        url = self.getHostURL()
        if self.childID:
            fullRequest = {
                "method": "multipleRequest",
                "params": {
                    "requests": [
                        {
                            "method": "controlChild",
                            "params": {
                                "childControl": {
                                    "device_id": self.childID,
                                    "request_data": requestData,
                                }
                            },
                        }
                    ]
                },
            }
        else:
            fullRequest = requestData
        async with AsyncClient() as client:
            res = await client.post(
                url, data=json.dumps(fullRequest), headers=self.headers, verify=False
            )
        if not self.responseIsOK(res):
            data = res.json()
            if (
                not data
                or "error_code" not in data
                or data["error_code"] != -40401
                or loginRetryCount >= MAX_LOGIN_RETRIES
            ):
                raise ResponseException(
                    f'Error: {self.getErrorMessage(data["error_code"])}, Response: {json.dumps(data)}'
                )
            self.refreshStok()
            return await self.performRequest(requestData, loginRetryCount + 1)
        responseJSON = res.json()
        # strip away child device stuff to ensure consistent response format for HUB cameras
        if self.childID:
            responses = []
            for response in responseJSON["result"]["responses"]:
                if "method" in response and response["method"] == "controlChild":
                    if "response_data" in response["result"]:
                        responses.append(response["result"]["response_data"])
                    else:
                        responses.append(response["result"])
                else:
                    responses.append(response["result"])  # not sure if needed
            responseJSON["result"]["responses"] = responses
            return responseJSON["result"]["responses"][0]
        elif self.responseIsOK(res):
            return responseJSON
