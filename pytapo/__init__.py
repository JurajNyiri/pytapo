from datetime import datetime
import hashlib
import json

from httpx import AsyncClient
from pytapo.client.client import ensure_authenticated
from pytapo.const import MAX_LOGIN_RETRIES
from pytapo.detection.detection import DetectionInterface
from pytapo.detection.sound_detection import AudioDetection
from pytapo.error import ResponseException
from pytapo.home.home import HomeAssistantInterface
from pytapo.media_stream.session import HttpMediaSession
from pytapo.settings.device import DeviceInterface
from pytapo.settings.image import ImageInterface
from pytapo.settings.led import LEDInterface
from pytapo.settings.alarm import AlarmInterface
from pytapo.motor.presets import PresetInterface
from pytapo.recording.recording import RecordingInterface
from pytapo.motor.motor import MotorInterface

from pytapo.client.client import ClientInterface
from pytapo.utils import getErrorMessage


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
        self.deviceInterface = DeviceInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.presetInterface = PresetInterface(self.executeFunction)
        self.recordingInterface = RecordingInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.imageInterface = ImageInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.motorInterface = MotorInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.alarmInterface = AlarmInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.imageInterface = ImageInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.ledInterface = LEDInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.detectionInterface = DetectionInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.soundDetectionInterface = AudioDetection(
            self.performRequest, self.executeFunction, childID
        )
        self.homeAssistantInterface = HomeAssistantInterface(
            self.performRequest, self.executeFunction, childID
        )
        self.client = ClientInterface(
            host,
            user,
            password,
            cloudPassword,
            superSecretKey,
            self.performRequest,
            self.executeFunction,
            childID,
        )
        self.childID = childID
        self.mediaSession = HttpMediaSession(host, cloudPassword, superSecretKey)
        self.headers = self.client.headers

    def getBasicInfo(self) -> dict:
        """
        Returns the basic information about the device.
        """
        return self.deviceInterface.getBasicInfo()

    def isSupported(self) -> bool:
        """
        Returns True if the device is supported.
        """
        return self.presetInterface.isSupportingPresets() or {}

    def getMediaSession(self) -> HttpMediaSession:
        """
        Returns the HttpMediaSession instance.
        """
        return HttpMediaSession(self.host, self.cloudPassword, self.superSecretKey)

    def getHostURL(self) -> str:
        """
        Returns the host URL with stok for further API calls.
        """
        return f"https://{self.host}/stok={self.stok}/ds"

    def getStreamURL(self) -> str:
        """
        Returns the Stream URL for video streaming.
        """
        return f"{self.host}:8800"

    def reboot(self) -> bool:
        """
        Reboots the device.
        """
        return self.executeFunction("rebootDevice", {"system": {"reboot": "null"}})

    def getErrorMessage(self, errorCode) -> str:
        """
        Returns the error message for given error code.
        """
        return getErrorMessage(errorCode)

    def getMost(self) -> dict:
        """
        Returns the most information about the device.
        """
        return self.homeAssistantInterface.getMost()

    def getTime(self) -> datetime:
        """
        Returns the device time.
        """
        return self.deviceInterface.getTime()

    def setDayNightMode(self, mode: str) -> bool:
        """
        Sets the day/night mode of the device.
        """
        return self.deviceInterface.setDayNightMode(mode)

    def setMotionDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the motion detection of the device.
        """
        return self.detectionInterface.setMotionDetection(enabled)

    def setPersonDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the person detection of the device.
        """
        return self.detectionInterface.setPersonDetection(enabled)

    def setPetDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the pet detection of the device.
        """
        return self.detectionInterface.setPetDetection(enabled)

    def setVehicleDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the vehicle detection of the device.
        """
        return self.detectionInterface.setVehicleDetection(enabled)

    def setAlarm(self, enabled: bool) -> bool:
        """
        Enables or disables the alarm of the device.
        """
        return self.alarmInterface.setAlarm(enabled)

    def startManualAlarm(self) -> bool:
        """
        Starts the manual alarm of the device.
        """
        return self.alarmInterface.start_manual_alarm()

    def stopManualAlarm(self) -> bool:
        """
        Stops the manual alarm of the device.
        """
        return self.alarmInterface.stop_manual_alarm()

    def getTimeCorrection(self) -> bool:
        """
        Corrects the time of the device.
        """
        return self.deviceInterface.getTimeCorrection()

    def setLEDEnabled(self, enabled: bool) -> bool:
        """
        Enables or disables the LED of the device.
        """
        return self.ledInterface.setLEDEnabled(enabled)

    def calibrateMotor(self) -> bool:
        """
        Calibrates the motor of the device.
        """
        return self.motorInterface.calibrateMotor()

    def deletePreset(self, presetID: int) -> bool:
        """
        Deletes the preset with given ID.
        """
        return self.presetInterface.deletePreset(presetID)

    def getPresets(self) -> list:
        """
        Returns the list of presets.
        """
        return self.presetInterface.getPresets()

    def savePreset(self, presetID: int) -> bool:
        """
        Saves the preset with given ID.
        """
        return self.presetInterface.savePreset(presetID)

    def ensureAuthenticated(self) -> bool:
        """
        Ensures that the client is authenticated.
        """
        return self.client.ensureAuthenticated()

    def format(self, data: dict) -> dict:
        """
        Formats the data to be sent to the device.
        """
        return self.deviceInterface.format(data)

    def getAlarmConfig(self) -> dict:
        """
        Returns the alarm configuration.
        """
        return self.alarmInterface.getAlarmConfig()

    def getAudioSpec(self) -> dict:
        """
        Returns the audio specification.
        """
        return self.deviceInterface.getAudioSpec()

    def getChildDevices(self) -> dict:
        """
        Returns the child devices.
        """
        return self.deviceInterface.getChildDevices()

    def getCommonImage(self) -> dict:
        """
        Returns the common image.
        """
        return self.imageInterface.getCommonImage()

    def getForceWhitelampState(self) -> dict:
        """
        Returns the force white lamp state.
        """
        return self.imageInterface.getForceWhitelampState()

    def getGlassBreakDetection(self) -> dict:
        """
        Returns the glass break detection.
        """
        return self.soundDetectionInterface.getGlassBreakDetection()

    def setGlassBreakDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the glass break detection of the device.
        """
        return self.soundDetectionInterface.setGlassBreakDetection(enabled)

    def getMeowDetection(self) -> dict:
        """
        Returns the meow detection.
        """
        return self.soundDetectionInterface.getMeowDetection()

    def setMeowDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the meow detection of the device.
        """
        return self.soundDetectionInterface.setMeowDetection(enabled)

    def setBarkDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the bark detection of the device.
        """
        return self.soundDetectionInterface.setBarkDetection(enabled)

    def setBabyCryDetection(self, enabled: bool) -> bool:
        """
        Enables or disables the baby cry detection of the device.
        """
        return self.soundDetectionInterface.setBabyCryDetection(enabled)

    def getBabyCryDetection(self) -> dict:
        """
        Returns the baby cry detection.
        """
        return self.soundDetectionInterface.getBabyCryDetection()

    def getImageFlipVertical(self) -> dict:
        """
        Returns the image flip vertical.
        """
        return self.imageInterface.getImageFlipVertical()

    def setImageFlipVertical(self, enabled: bool) -> bool:
        """
        Enables or disables the image flip vertical of the device.
        """
        return self.imageInterface.setImageFlipVertical(enabled)

    def getLensDistortionCorrection(self) -> dict:
        """
        Returns the lens distortion correction.
        """
        return self.imageInterface.getLensDistortionCorrection()

    def setLensDistortionCorrection(self, enabled: bool) -> bool:
        """
        Enables or disables the lens distortion correction of the device.
        """
        return self.imageInterface.setLensDistortionCorrection(enabled)

    def setForceWhitelampState(self, enabled: bool) -> bool:
        """
        Enables or disables the force whitelamp state.
        """
        return self.imageInterface.setForceWhitelampState(enabled)

    def getLED(self) -> dict:
        """
        Returns the LED.
        """
        return self.ledInterface.getLED()

    def setLED(self, enabled: bool) -> bool:
        """
        Enables or disables the LED of the device.
        """
        return self.ledInterface.setLED(enabled)

    def getLightFrequencyMode(self) -> dict:
        """
        Returns the light frequency mode.
        """
        return self.ledInterface.get_light_frequency_mode()

    def setLightFrequencyMode(self, mode: str) -> bool:
        """
        Sets the light frequency mode of the device.
        """
        return self.ledInterface.set_light_frequency_mode(mode)

    def getMotionDetection(self) -> dict:
        """
        Returns the motion detection.
        """
        return self.detectionInterface.getMotionDetection()

    def getMediaEncrypt(self) -> dict:
        """
        Returns the media encryption.
        """
        return self.deviceInterface.getMediaEncrypt()

    def setMediaEncrypt(self, enabled: bool) -> bool:
        """
        Enables or disables the media encryption of the device.
        """
        return self.deviceInterface.setMediaEncrypt(enabled)

    def getModuleSpec(self) -> dict:
        """
        Returns the module specification.
        """
        return self.deviceInterface.getModuleSpec()

    def getMotorCapability(self) -> dict:
        """
        Returns the motor capability.
        """
        return self.motorInterface.get_motor_capability()

    def setAutoTrackTarget(self, enabled: bool) -> bool:
        """
        Enables or disables the auto track target of the device.
        """
        return self.motorInterface.setAutoTrackTarget(enabled)

    def getVhttpd(self) -> dict:
        """
        Returns the vhttpd.
        """
        return self.deviceInterface.getVhttpd()

    def getHashCloudPassword(self) -> str:
        """
        Returns the hashed cloud password.
        """
        return self.client.hashedCloudPassword

    def getHashPassword(self) -> str:
        """
        Returns the hashed password.
        """
        return self.client.hashedPassword

    def refreshStok(self) -> str:
        """
        Refreshes the stok.
        """
        self.client.refreshStok()

    def responseIsOK(self, response) -> bool:
        """
        Checks if the response is OK.
        """
        return self.client.responseIsOK(response)

    def setCruise(self, enabled: bool) -> bool:
        """
        Enables or disables the cruise of the device.
        """
        return self.detectionInterface.setCruise(enabled)

    def setOsd(self, enabled: bool) -> bool:
        """
        Enables or disables the OSD of the device.
        """
        return self.deviceInterface.setOsd(enabled)

    def getOsd(self) -> dict:
        """
        Returns the OSD.
        """
        return self.deviceInterface.getOsd()

    def startFirmwareUpgrade(self, url: str) -> bool:
        """
        Starts the firmware upgrade of the device.
        """
        return self.deviceInterface.startFirmwareUpgrade(url)

    def executeFunction(self, method: str, params: dict, retry=False) -> dict:
        """
        Executes a method with given params. If the method is "multipleRequest", it performs the request for each param.
        In case of error, it retries the execution once.

        :param method: The method to execute.
        :param params: The params to pass to the method.
        :param retry: Whether to retry the execution or not.
        :return: The result of the execution.
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
