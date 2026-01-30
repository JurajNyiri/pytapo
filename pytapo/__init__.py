#
# Author: See contributors at https://github.com/JurajNyiri/pytapo/graphs/contributors
#
import hashlib
import json
import requests
import asyncio
import logging
from logging import Handler
import re
import uuid

from kasa.transports import KlapTransportV2, KlapTransport
from kasa.exceptions import (
    AuthenticationError,
    KasaException,
    DeviceError,
    UnsupportedDeviceError,
)
from kasa import DeviceConfig, Credentials, Discover

from datetime import datetime, timedelta
from warnings import warn

from .const import ERROR_CODES, MAX_LOGIN_RETRIES, EncryptionMethod
from .media_stream.session import HttpMediaSession
from .media_stream._utils import StreamType

LOGGER = logging.getLogger("pytapo")


# Supress Error messages, we handle them internally and log if necessary
class SuppressPythonKasaLogs(logging.Filter):
    def filter(self, record):
        return (
            "Response status is 403" not in record.getMessage()
            and "Server disconnected" not in record.getMessage()
            and "Response status is 400, Request was" not in record.getMessage()
        )


class Tapo:
    def debugLog(self, msg):
        if self.printDebugInformation is True:
            print(msg)
        elif callable(self.printDebugInformation):
            self.printDebugInformation(msg)

    def getControlHost(self):
        return f"{self.host}:{self.controlPort}"

    def __init__(
        self,
        host,
        user,
        password,
        cloudPassword="",
        superSecretKey="",
        childID=None,
        reuseSession=False,
        printDebugInformation=False,
        controlPort=443,
        retryStok=True,
        redactConfidentialInformation=True,
        streamPort=8800,
        isKLAP=None,
        KLAPVersion=None,
        hass=None,
        playerID=None,
    ):
        logger = logging.getLogger("kasa.transports.klaptransport")
        logger.addFilter(SuppressPythonKasaLogs())

        self.redactConfidentialInformation = redactConfidentialInformation
        self.printDebugInformation = printDebugInformation
        self.host = host
        if hass is not None:
            self.hass = hass
        else:
            self.hass = None
        if controlPort is None:
            self.controlPort = 443
        else:
            self.controlPort = controlPort
        if isKLAP is not None:
            self.isKLAP = isKLAP
        else:
            self.isKLAP = self._isKLAP()
        if KLAPVersion is not None:
            self.KLAPVersion = KLAPVersion
        else:
            self.KLAPVersion = None

        if playerID is None:
            self.playerID = str(uuid.uuid4())
        else:
            self.playerID = playerID

        # python-kasa device handle
        self.dev = None
        self._kasa_ready = False
        self._loop = None
        self._last_kasa_unknown_code = None
        self._kasa_warn_handler = None

        self.klapTransport = None
        self.user = user
        self.password = password
        self.cloudPassword = cloudPassword
        self.superSecretKey = superSecretKey
        self.userID = False
        self.childID = childID
        self.timeCorrection = False
        self.reuseSession = reuseSession
        self.isSecureConnectionCached = None
        if streamPort is None:
            self.streamPort = 8800
        else:
            self.streamPort = streamPort
        self.headers = {
            "Host": self.getControlHost(),
            "Referer": "https://{host}".format(host=self.getControlHost()),
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "Tapo CameraClient Android",
            "Connection": "close",
            "requestByApp": "true",
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.hashedPassword = hashlib.md5(password.encode("utf8")).hexdigest().upper()
        self.hashedSha256Password = (
            hashlib.sha256(password.encode("utf8")).hexdigest().upper()
        )
        self.hashedCloudPassword = (
            hashlib.md5(cloudPassword.encode("utf8")).hexdigest().upper()
        )
        self.session = False

        self.basicInfo = self.getBasicInfo()
        if "type" in self.basicInfo:
            self.deviceType = self.basicInfo["type"]
        elif (
            "device_info" in self.basicInfo
            and "basic_info" in self.basicInfo["device_info"]
            and "device_type" in self.basicInfo["device_info"]["basic_info"]
        ):
            self.deviceType = self.basicInfo["device_info"]["basic_info"]["device_type"]
        else:
            raise Exception("Failed to detect device type.")
        if self.deviceType == "SMART.TAPOCHIME":
            self.pairList = self.getPairList()

        self.presets = self.isSupportingPresets()
        if not self.presets:
            self.presets = {}

    def isSupportingPresets(self):
        try:
            presets = self.getPresets()
            return presets
        except Exception:
            return False

    def getStreamURL(self):
        return "{host}:{streamPort}".format(host=self.host, streamPort=self.streamPort)

    def _isKLAP(self, timeout=2):
        try:
            url = f"http://{self.host}:{self.controlPort}"
            response = requests.get(url, timeout=timeout)
            return "200 OK" in response.text
        except requests.RequestException:
            return False

    async def initiateKlapTransport(self, version=1):
        try:
            if self.klapTransport is None:
                creds = Credentials(self.user, self.password)
                config = DeviceConfig(
                    self.host, port_override=self.controlPort, credentials=creds
                )
                if version == 1:
                    transport = KlapTransport(config=config)
                elif version == 2:
                    transport = KlapTransportV2(config=config)
                await transport.perform_handshake()
                self.klapTransport = transport
                return self.klapTransport
        finally:
            await transport.close()

    async def sendKlapRequest(self, request, retry=0):
        try:
            if self.klapTransport is None:
                await self.ensureAuthenticated()
            response = await self.klapTransport.send(json.dumps(request))
            return response
        except Exception as err:
            if (
                "Response status is 403, Request was" in str(err)
                or "Response status is 400, Request was" in str(err)
                or "Server disconnected" in str(err)
            ):
                raise Exception("PyTapo KLAP Error #6: " + str(err))

            self.debugLog("Retrying request... Error: " + str(err))
            if retry < 5:
                await self.ensureAuthenticated()
                return await self.sendKlapRequest(request, retry + 1)
            else:
                raise Exception("PyTapo KLAP Error #1: " + str(err))
        finally:
            if self.klapTransport is not None:
                await self.klapTransport.close()

    async def ensureAuthenticated(self):
        # Use python-kasa for auth/transport
        if self.isKLAP:
            if self.klapTransport is None:
                if self.KLAPVersion is None:
                    try:
                        await self.initiateKlapTransport(1)
                        self.KLAPVersion = 1
                    except AuthenticationError:
                        try:
                            await self.initiateKlapTransport(2)
                            self.KLAPVersion = 2
                        except AuthenticationError:
                            raise Exception("Invalid authentication data")
                        except Exception as err:
                            raise Exception("PyTapo KLAP Error #2: " + str(err))
                    except Exception as err:
                        raise Exception("PyTapo KLAP Error #3: " + str(err))
                else:
                    if self.KLAPVersion == 1:
                        try:
                            await self.initiateKlapTransport(1)
                        except AuthenticationError:
                            raise Exception("Invalid authentication data")
                        except Exception as err:
                            raise Exception("PyTapo KLAP Error #4: " + str(err))
                    elif self.KLAPVersion == 2:
                        try:
                            await self.initiateKlapTransport(2)
                        except AuthenticationError:
                            raise Exception("Invalid authentication data")
                        except Exception as err:
                            raise Exception("PyTapo KLAP Error #5: " + str(err))
            return True

        if self.dev is None:
            creds = Credentials(self.user, self.password)
            try:
                self.dev = await Discover.discover_single(self.host, credentials=creds)
            except TimeoutError as err:
                raise Exception(
                    f"Failed to establish a new connection: {str(err)}"
                ) from err
            if self.dev is None:
                raise Exception("Device not found via python-kasa Discover")
            self.debugLog(
                f"kasa discover_single: host={self.host} proto={type(self.dev.protocol).__name__}"
            )
            self._install_kasa_warn_handler()
        if not self._kasa_ready:
            try:
                self.debugLog("kasa update: starting initial state fetch")
                self._log_kasa_connection_info()
                await self.dev.update()
                self._kasa_ready = True
            except AuthenticationError as err:
                self.debugLog(f"kasa update failed (auth): {err}")
                await self._close_kasa_device()
                raise Exception("Invalid authentication data") from err
            except DeviceError as err:
                self.debugLog(f"kasa update failed (device error): {err}")
                await self._close_kasa_device()
                raise
            except Exception as err:
                self.debugLog(f"kasa update failed: {err}")
                await self._close_kasa_device()
                raise
        return True

    async def _kasa_query(self, payload):
        """Send a raw payload through python-kasa transport."""
        await self.ensureAuthenticated()
        self.debugLog("Sending payload:")
        self.debugLog(payload)
        response = await self.dev.protocol.query(payload)
        self.debugLog("Response:")
        self.debugLog(response)
        return response

    def responseIsOK(self, res, data=None):
        self.debugLog("Verifying response...")
        if data is None:
            data = res
        if not isinstance(data, dict):
            return True
        return "error_code" not in data or data["error_code"] == 0

    def executeFunction(self, method, params, retry=False):
        if method == "multipleRequest":
            request_payload = {"multipleRequest": params or {}}
            resp = self.performRequest(request_payload)
            data = resp["result"]["responses"]
        else:
            req = {"multipleRequest": {"requests": [{"method": method}]}}
            if params is not None:
                req["multipleRequest"]["requests"][0]["params"] = params

            resp = self.performRequest(req)
            data = resp["result"]["responses"][0]

        if type(data) == list:
            return data

        if "result" in data and (
            "error_code" not in data
            or ("error_code" in data and data["error_code"] == 0)
        ):
            return data["result"]
        elif "method" in data and "error_code" in data and data["error_code"] == 0:
            return data
        else:
            if "error_code" in data and data["error_code"] == -64303 and retry is False:
                self.setCruise(False, retry=True)
                return self.executeFunction(method, params, True)
            raise Exception(
                "Error: {}, Response: {}".format(
                    (
                        data["err_msg"]
                        if "err_msg" in data
                        else self.getErrorMessage(data["error_code"])
                    ),
                    json.dumps(data),
                )
            )

    def executeAsyncExecutorJob(self, job, *args):
        if self.hass is None:
            # reuse a dedicated loop so kasa aiohttp sessions stay alive between calls
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(self._loop)
                return self._loop.run_until_complete(job(*args))
            finally:
                asyncio.set_event_loop(None)
        else:
            return asyncio.run_coroutine_threadsafe(job(*args), self.hass.loop).result()

    async def _close_kasa_device(self):
        try:
            if self.dev and getattr(self.dev, "protocol", None):
                await self.dev.protocol.close()
        except Exception:
            pass
        self.dev = None
        self._kasa_ready = False
        if self._kasa_warn_handler:
            logging.getLogger("kasa.protocols.smartcamprotocol").removeHandler(
                self._kasa_warn_handler
            )
            self._kasa_warn_handler = None
        self._last_kasa_unknown_code = None

    def _log_kasa_connection_info(self):
        ct = getattr(getattr(self.dev, "config", None), "connection_type", None)
        transport = getattr(self.dev, "protocol", None)
        transport_impl = getattr(transport, "_transport", None)

        device_info = {
            "alias": getattr(self.dev, "alias", None),
            "model": getattr(self.dev, "model", None),
            "mac": getattr(self.dev, "mac", None),
        }
        hw_info = getattr(self.dev, "hw_info", {}) or {}
        device_info["fw"] = hw_info.get("sw_ver") or hw_info.get("fw_ver")

        self.debugLog(f"kasa device: {device_info}")
        self.debugLog(f"kasa chosen encryption: {self.getEncryptionMethod()}")

        if ct:
            fields = {
                "device_family": getattr(ct, "device_family", None),
                "encryption_type": getattr(ct, "encryption_type", None),
                "https": getattr(ct, "https", None),
                "login_version": getattr(ct, "login_version", None),
                "http_port": getattr(ct, "http_port", None),
            }
            self.debugLog(
                f"kasa connection_type: {fields}, "
                f"protocol={type(transport).__name__}, "
                f"transport={type(transport_impl).__name__ if transport_impl else None}"
            )
        else:
            self.debugLog("kasa connection_type: <unavailable>")

    def _install_kasa_warn_handler(self):
        if self._kasa_warn_handler:
            return

        class _WarnHandler(Handler):
            def __init__(self, outer):
                super().__init__(level=logging.WARNING)
                self.outer = outer

            def emit(self, record):
                msg = record.getMessage()
                m = re.search(r"received unknown error code: (-?\d+)", msg)
                if m:
                    try:
                        self.outer._last_kasa_unknown_code = int(m.group(1))
                    except Exception:
                        pass
                    # downgrade the log so it doesn't surface as a warning
                    record.levelno = logging.DEBUG
                    record.levelname = "DEBUG"

        self._kasa_warn_handler = _WarnHandler(self)
        logging.getLogger("kasa.protocols.smartcamprotocol").addHandler(
            self._kasa_warn_handler
        )

    def _format_device_error(self, err):
        """Return a user-friendly message for kasa DeviceError."""
        msg = str(err)
        code = getattr(err, "error_code", None)
        if code is not None and str(code) in ERROR_CODES:
            return self.getErrorMessage(str(code))
        # use the last unknown code observed from kasa warnings if available
        if (
            self._last_kasa_unknown_code
            and str(self._last_kasa_unknown_code) in ERROR_CODES
        ):
            errMsg = self.getErrorMessage(str(self._last_kasa_unknown_code))
            self._last_kasa_unknown_code = None
            return errMsg
        if self._last_kasa_unknown_code:
            code = self._last_kasa_unknown_code
            self._last_kasa_unknown_code = None
            return f"Device error {code}"
        return f"Device error: {msg}"

    def performRequest(self, requestData, loginRetryCount=0):
        try:
            self.executeAsyncExecutorJob(self.ensureAuthenticated)
        except AuthenticationError as err:
            self.executeAsyncExecutorJob(self._close_kasa_device)
            raise Exception("Invalid authentication data") from err
        except DeviceError as err:
            errMsg = self._format_device_error(err)
            if "Device blocked for" in errMsg:
                raise Exception(f"Temporary Suspension: {str(errMsg)}") from err
            raise Exception(self._format_device_error(err)) from err
        except Exception as err:
            if loginRetryCount < MAX_LOGIN_RETRIES:
                self.executeAsyncExecutorJob(self._close_kasa_device)
                return self.performRequest(requestData, loginRetryCount + 1)
            raise err
        authValid = True

        if self.isKLAP:
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

            responseJSON = self.executeAsyncExecutorJob(
                self.sendKlapRequest, fullRequest
            )
            res = None
            if (
                "result" in responseJSON
                and "responses" in responseJSON["result"]
                and len(responseJSON["result"]["responses"]) == 1
            ):
                if not self.responseIsOK(res, responseJSON["result"]["responses"][0]):
                    authValid = False
        else:
            if self.childID:
                fullRequest = {
                    "multipleRequest": {
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
                    }
                }
            else:
                fullRequest = requestData

            try:
                responseJSON = self.executeAsyncExecutorJob(
                    self._kasa_query, fullRequest
                )
            except DeviceError as err:
                errMsg = self._format_device_error(err)
                if "Device blocked for" in errMsg:
                    raise Exception(f"Temporary Suspension: {str(errMsg)}") from err
                raise Exception(self._format_device_error(err)) from err
            except (AuthenticationError, KasaException) as err:
                if loginRetryCount < MAX_LOGIN_RETRIES:
                    self.dev = None
                    self._kasa_ready = False
                    return self.performRequest(requestData, loginRetryCount + 1)
                raise Exception(f"Invalid authentication data (kasa): {err}")
            except Exception as err:
                if loginRetryCount < MAX_LOGIN_RETRIES:
                    self.dev = None
                    self._kasa_ready = False
                    return self.performRequest(requestData, loginRetryCount + 1)
                raise Exception(f"PyTapo Kasa Error: {err}")

            if not self.responseIsOK(None, responseJSON):
                authValid = False
            # normalize kasa shape to legacy result/responses for downstream code
            if "result" not in responseJSON and "multipleRequest" in responseJSON:
                self.debugLog("Normalizing Kasa response...")
                responseJSON = {"result": responseJSON["multipleRequest"]}
                self.debugLog(f"Normalized: {responseJSON}")

        if not authValid:
            if loginRetryCount < MAX_LOGIN_RETRIES:
                self.debugLog("Retrying request...")
                if self.isKLAP:
                    self.klapTransport = None
                else:
                    self.dev = None
                    self._kasa_ready = False
                return self.performRequest(requestData, loginRetryCount + 1)
            else:
                raise Exception(
                    "Error: {}, Response: {}".format(
                        self.getErrorMessage(
                            responseJSON.get("error_code")
                            if isinstance(responseJSON, dict)
                            else None
                        ),
                        json.dumps(responseJSON),
                    )
                )

        # strip away child device stuff to ensure consistent response format for HUB cameras
        if self.childID:
            self.debugLog("Handling response for child...")
            self.debugLog(responseJSON)
            if (
                "result" in responseJSON
                and "responses" in responseJSON["result"]
                and len(responseJSON["result"]["responses"]) >= 1
            ):
                responses = []
                for response in responseJSON["result"]["responses"]:
                    if "method" in response and response["method"] == "controlChild":
                        if "response_data" in response.get("result", {}):
                            responses.append(response["result"]["response_data"])
                        else:
                            responses.append(response.get("result"))
                    else:
                        responses.append(response.get("result"))
                responseJSON["result"]["responses"] = responses
                self.debugLog("Returning:")
                self.debugLog(responseJSON["result"]["responses"][0])
                return responseJSON["result"]["responses"][0]
        else:
            if self.isKLAP:
                self.debugLog("Device is KLAP")
                if self.responseIsOK(None, responseJSON):
                    self.debugLog("Returning:")
                    self.debugLog(responseJSON)
                    return responseJSON
                else:
                    raise Exception(
                        "Error: {}, Response: {}".format(
                            self.getErrorMessage(responseJSON["error_code"]),
                            json.dumps(responseJSON),
                        )
                    )
            else:
                self.debugLog("Device is not a child and not KLAP.")
                self.debugLog("Returning:")
                self.debugLog(responseJSON)
                return responseJSON

    def getMediaSession(self, stream_type: StreamType = None, start_time=""):
        query_params = {}
        if self.childID is not None:
            if stream_type == StreamType.Download:
                query_params = {
                    "deviceId": self.childID,
                    "playerId": self.playerID,
                    "type": "sdvod",
                    "start_time": start_time,
                }
            elif stream_type == StreamType.Stream:
                query_params = {
                    "deviceId": self.childID,
                    "playerId": self.playerID,
                    "type": "video",
                }
            else:
                raise Exception(
                    "Incorrect stream type. Choose StreamType.Stream or StreamType.Download."
                )
        return HttpMediaSession(
            self.host,
            self.cloudPassword,
            self.superSecretKey,
            self.getEncryptionMethod(),
            port=self.streamPort,
            query_params=query_params,
        )  # pragma: no cover

    def getEncryptionMethod(self):
        """
        Pick the password digest method for media/auth based on connection details.
        - KLAP devices use SHA256.
        - For python-kasa devices, prefer SHA256 when login_version >=2, else MD5.
        Defaults to SHA256 if unknown.
        """
        if self.isKLAP:
            return EncryptionMethod.SHA256
        if self.dev and getattr(self.dev, "config", None):
            ct = getattr(self.dev.config, "connection_type", None)
            login_version = getattr(ct, "login_version", None) if ct else None
            if login_version is not None and login_version < 2:
                return EncryptionMethod.MD5
        return EncryptionMethod.SHA256

    def getChildDevices(self):
        childDevices = self.performRequest(
            {"getChildDeviceList": {"childControl": {"start_index": 0}}}
        )
        return childDevices["result"]["child_device_list"]

    def getTimeCorrection(self):
        if self.timeCorrection is False:
            currentTime = self.getTime()

            timeReturned = (
                "system" in currentTime
                and "clock_status" in currentTime["system"]
                and "seconds_from_1970" in currentTime["system"]["clock_status"]
            )
            nowTS = int(datetime.timestamp(datetime.now()))
            if timeReturned:
                self.timeCorrection = (
                    nowTS - currentTime["system"]["clock_status"]["seconds_from_1970"]
                )
            else:
                timeReturned = "timestamp" in currentTime
                if timeReturned:
                    self.timeCorrection = nowTS - currentTime["timestamp"]
        return self.timeCorrection

    def getEvents(self, startTime=False, endTime=False):
        timeCorrection = self.getTimeCorrection()
        if timeCorrection is False:
            raise Exception("Failed to get correct camera time.")

        nowTS = int(datetime.timestamp(datetime.now()))
        if startTime is False:
            startTime = nowTS + (-1 * timeCorrection) - (10 * 60)
        if endTime is False:
            endTime = nowTS + (-1 * timeCorrection) + 60

        responseData = self.executeFunction(
            "searchDetectionList",
            {
                "playback": {
                    "search_detection_list": {
                        "start_index": 0,
                        "channel": 0,
                        "start_time": startTime,
                        "end_time": endTime,
                        "end_index": 999,
                    }
                }
            },
        )
        events = []

        detectionsReturned = (
            "playback" in responseData
            and "search_detection_list" in responseData["playback"]
        )

        if detectionsReturned:
            for event in responseData["playback"]["search_detection_list"]:
                event["start_time"] = event["start_time"] + timeCorrection
                event["end_time"] = event["end_time"] + timeCorrection
                event["startRelative"] = nowTS - event["start_time"]
                event["endRelative"] = nowTS - event["end_time"]
                events.append(event)
        return events

    def getVideoQualities(self):
        return self.executeFunction(
            "getVideoQualities",
            {"video": {"name": ["main"]}},
        )

    def getVideoCapability(self):
        return self.executeFunction(
            "getVideoCapability",
            {"video_capability": {"name": "main"}},
        )

    # returns empty response for child devices
    def getOsd(self):
        # no, asking for all does not work...
        if self.childID:
            return self.executeFunction(
                "getOsd",
                {"OSD": {"name": ["logo", "date", "label"]}},
            )
        else:
            return self.executeFunction(
                "getOsd",
                {"OSD": {"name": ["date", "week", "font"], "table": ["label_info"]}},
            )

    def setOsd(
        self,
        label,
        dateEnabled=True,
        labelEnabled=False,
        weekEnabled=False,
        dateX=0,
        dateY=0,
        labelX=0,
        labelY=500,
        weekX=0,
        weekY=0,
    ):
        if self.childID:
            raise Exception("setOsd not supported for child devices yet")
        data = {
            "set": {
                "OSD": {
                    "date": {
                        "enabled": "on" if dateEnabled else "off",
                        "x_coor": dateX,
                        "y_coor": dateY,
                    },
                    "week": {
                        "enabled": "on" if weekEnabled else "off",
                        "x_coor": weekX,
                        "y_coor": weekY,
                    },
                    "font": {
                        "color": "white",
                        "color_type": "auto",
                        "display": "ntnb",
                        "size": "auto",
                    },
                    "label_info_1": {
                        "enabled": "on" if labelEnabled else "off",
                        "x_coor": labelX,
                        "y_coor": labelY,
                    },
                },
            }
        }

        if len(label) >= 16:
            raise Exception("Error: Label cannot be longer than 16 characters")
        elif len(label) == 0:
            data["OSD"]["label_info_1"]["enabled"] = "off"
        else:
            data["OSD"]["label_info_1"]["text"] = label
        if (
            dateX > 10000
            or dateX < 0
            or labelX > 10000
            or labelX < 0
            or weekX > 10000
            or weekX < 0
            or dateY > 10000
            or dateY < 0
            or labelY > 10000
            or labelY < 0
            or weekY > 10000
            or weekY < 0
        ):
            raise Exception("Error: Incorrect corrdinates, must be between 0 and 10000")

        return self.performRequest(data)

    # does not work for child devices, function discovery needed
    def getModuleSpec(self):
        return self.performRequest({"get": {"function": {"name": ["module_spec"]}}})

    def getPrivacyMode(self):
        data = self.executeFunction(
            "getLensMaskConfig",
            {"lens_mask": {"name": ["lens_mask_info"]}},
        )
        return data["lens_mask"]["lens_mask_info"]

    def getMediaEncrypt(self):
        data = self.executeFunction(
            "getMediaEncrypt",
            {"cet": {"name": ["media_encrypt"]}},
        )
        return data["cet"]["media_encrypt"]

    def getAlarm(self):
        # ensure reverse compatibility, simulate the same response for children devices
        if self.childID:
            data = self.getAlarmConfig()

            # replace "siren" with "sound", some cameras call it siren, some sound
            for i in range(len(data[0]["result"]["alarm_mode"])):
                if data[0]["result"]["alarm_mode"][i] == "siren":
                    data[0]["result"]["alarm_mode"][i] = "sound"
            return {
                "alarm_type": "0",
                "light_type": "0",
                "enabled": data[0]["result"]["enabled"],
                "alarm_mode": data[0]["result"]["alarm_mode"],
            }
        else:
            return self.executeFunction(
                "getLastAlarmInfo",
                {"msg_alarm": {"name": ["chn1_msg_alarm_info"]}},
            )["msg_alarm"]["chn1_msg_alarm_info"]

    def getAlarmConfig(self):
        return self.executeFunction(
            "multipleRequest",
            {
                "requests": [
                    {"method": "getAlarmConfig", "params": {"msg_alarm": {}}},
                    {"method": "getAlarmPlan", "params": {"msg_alarm_plan": {}}},
                    {"method": "getSirenTypeList", "params": {"msg_alarm": {}}},
                    {"method": "getLightTypeList", "params": {"msg_alarm": {}}},
                    {"method": "getSirenStatus", "params": {"msg_alarm": {}}},
                ]
            },
        )

    def setRingStatus(self, enabled):
        params = {"enabled": "on" if enabled else "off"}

        return self.executeFunction(
            "setRingStatus",
            {"ring": {"status": params}},
        )

    def setChargingMode(self, chargingPrivacyMode):
        params = {"charging_privacy_mode": "on" if chargingPrivacyMode else "off"}

        return self.executeFunction(
            "setChargingMode", {"battery": {"charging_mode": params}}
        )

    def setBatteryPowerSave(self, enabled):
        params = {"enabled": "auto" if enabled else "off"}

        return self.executeFunction(
            "setBatteryPowerSave",
            {"battery": {"power_save": params}},
        )

    def setClipsConfig(self, clipsLength=None, recordBuffer=None, retriggerTime=None):
        params = {}
        if clipsLength is not None:
            params["clips_length"] = int(clipsLength)
        if recordBuffer is not None:
            params["record_buffer"] = int(recordBuffer)
        if retriggerTime is not None:
            params["retrigger_time"] = int(retriggerTime)

        if params["retrigger_time"] > 60 or params["retrigger_time"] < 0:
            raise Exception("Retrigger time has to be between 0 and 60.")

        if params["clips_length"] < 20 or params["clips_length"] > 120:
            raise Exception("Clips Length has to be between 20 and 120.")

        if params["record_buffer"] < 3 or params["record_buffer"] > 10:
            raise Exception("Record buffer has to be between 3 and 10.")
        return self.executeFunction(
            "setClipsConfig",
            {"clips": {"config": params}},
        )

    def setBatteryOperatingMode(self, mode):
        availableOperatingModes = self.getBatteryOperatingModeParam()["battery"][
            "operating_mode_param"
        ]["config_array"]
        modeIsValid = False
        for availableMode in availableOperatingModes:
            if availableMode["mode"] == mode:
                modeIsValid = True

        if modeIsValid:
            params = {"follow_config": False, "mode": mode}

            return self.executeFunction(
                "setBatteryOperatingMode",
                {"battery": {"operating": params}},
            )
        else:
            raise Exception(f"Mode {mode} is invalid.")

    def setBatteryConfig(self, showOnLiveView=None, showPercentage=None):
        params = {}

        if showOnLiveView is not None:
            params["show_on_liveview"] = "on" if showOnLiveView else "off"

        if showPercentage is not None:
            params["show_percentage"] = "on" if showPercentage else "off"

        return self.executeFunction(
            "setBatteryConfig",
            {"battery": {"config": params}},
        )

    def setPirSensitivity(self, sensitivity: int):
        params = {"sensitivity": str(sensitivity)}

        if sensitivity >= 10 and sensitivity <= 100:
            return self.executeFunction(
                "setPirSensitivity",
                {"pir": {"config": params}},
            )

        else:
            raise Exception("PIR sensitivity has to be between 10 and 100")

    def setWakeUpConfig(self, wakeUpType):
        if wakeUpType == "doorbell" or wakeUpType == "detection":
            return self.executeFunction(
                "setWakeUpConfig", {"wake_up": {"config": {"wake_up_type": wakeUpType}}}
            )

    def setChimeRingPlan(self, enabled=None, ringPlan=None):
        params = {}
        if enabled is None or ringPlan is None:
            chimeRingPlan = self.getChimeRingPlan()

        if enabled is not None:
            params["enabled"] = "on" if enabled else "off"
        else:
            params["enabled"] = chimeRingPlan["chime_ring_plan"][
                "chn1_chime_ring_plan"
            ]["enabled"]

        if ringPlan is not None:
            params["ring_plan_1"] = ringPlan
        else:
            params["ring_plan_1"] = chimeRingPlan["chime_ring_plan"][
                "chn1_chime_ring_plan"
            ]["ring_plan_1"]

        return self.executeFunction(
            "setChimeRingPlan",
            {"chime_ring_plan": {"chn1_chime_ring_plan": params}},
        )

    def setTimezone(self, timezone, zoneID, timingMode="ntp"):
        return self.executeFunction(
            "setTimezone",
            {
                "system": {
                    "basic": {
                        "timing_mode": timingMode,
                        "timezone": timezone,
                        "zone_id": zoneID,
                    }
                }
            },
        )

    def getTimezone(self):
        return self.executeFunction("getTimezone", {"system": {"name": ["basic"]}})

    def getClipsConfig(self):
        return self.executeFunction("getClipsConfig", {"clips": {"name": "config"}})

    def getRingStatus(self):
        return self.executeFunction("getRingStatus", {"ring": {"name": "status"}})

    def getWakeUpConfig(self):
        return self.executeFunction("getWakeUpConfig", {"wake_up": {"name": "config"}})

    def getChimeCtrlList(self):
        return self.executeFunction(
            "getChimeCtrlList", {"chime_ctrl": {"get_paired_device_list": {}}}
        )

    def getPairList(self):
        return self.executeFunction("get_pair_list", None)

    def setHubSirenStatus(self, status):
        return self.executeFunction(
            "setSirenStatus", {"siren": {"status": "on" if status else "off"}}
        )

    def setSirenStatus(self, status):
        return self.executeFunction(
            "setSirenStatus", {"msg_alarm": {"status": "on" if status else "off"}}
        )

    def setHDR(self, status):
        return self.executeFunction(
            "setHDR",
            {"video": {"set_hdr": {"hdr": 1 if status else 0, "secname": "main"}}},
        )

    def getHubSirenStatus(self):
        return self.executeFunction("getSirenStatus", {"siren": {}})

    def getHubStorage(self):
        return self.executeFunction(
            "getHubStorage", {"hub_manage": {"name": "hub_storage_info"}}
        )

    def setHubSirenConfig(self, duration=None, siren_type=None, volume=None):
        params = {"siren": {}}
        if duration is not None:
            params["siren"]["duration"] = duration
        if siren_type is not None:
            params["siren"]["siren_type"] = siren_type
        if volume is not None:
            params["siren"]["volume"] = volume
        return self.executeFunction("setSirenConfig", params)

    def getHubSirenConfig(self):
        return self.executeFunction("getSirenConfig", {"siren": {}})

    def getAlertConfig(self, includeCapability=False, includeUserDefinedAudio=True):
        data = {
            "msg_alarm": {
                "name": ["chn1_msg_alarm_info"],
            }
        }
        if includeCapability:
            data["msg_alarm"]["name"].append("capability")
        if includeUserDefinedAudio:
            data["msg_alarm"]["table"] = ["usr_def_audio"]
        return self.executeFunction(
            "getAlertConfig",
            data,
        )

    def getHubSirenTypeList(self):
        return self.executeFunction("getSirenTypeList", {"siren": {}})

    def getAlertTypeList(self):
        return self.executeFunction(
            "getAlertTypeList", {"msg_alarm": {"name": "alert_type"}}
        )

    def getDayNightModeConfig(self):
        return self.executeFunction(
            "getDayNightModeConfig",
            {"image": {"name": "common"}},
        )

    def getThirdAccount(self):
        return self.executeFunction(
            "getThirdAccount",
            {"user_management": {"name": ["third_account"]}},
        )

    def getTapoCareServiceList(self):
        return self.executeFunction(
            "getTapoCareServiceList",
            {"tapo_care": {"name": ["service_list"]}},
        )

    def getCoverConfig(self):
        return self.executeFunction(
            "getCoverConfig",
            {"cover": {"name": ["cover"]}},
        )

    def setCoverConfig(self, enabled: bool):
        return self.executeFunction(
            "setCoverConfig",
            {"cover": {"cover": {"enabled": "on" if enabled else "off"}}},
        )

    def getCoverRegion(self):
        return self.executeFunction(
            "getCoverConfig",
            {"cover": {"table": ["region_info"]}},
        )

    def getFirmwareAutoUpgradeConfig(self):
        return self.executeFunction(
            "getFirmwareAutoUpgradeConfig",
            {"auto_upgrade": {"name": ["common"]}},
        )

    def getWifiBackup(self):
        return self.executeFunction(
            "getWifiBackup",
            {"hub_manage": {"name": "wifi_backup"}},
        )

    def startScanHub(self):
        return self.executeFunction(
            "startScanHub",
            {"hub_manage": {"start_scan_hub": {"unicast_hub_info": []}}},
        )

    def checkDiagnoseStatus(self):
        return self.executeFunction(
            "checkDiagnoseStatus",
            {"system": {"check_diagnose_status": ""}},
        )

    def getDiagnoseMode(self):
        return self.executeFunction(
            "getDiagnoseMode",
            {"system": {"name": "sys"}},
        )

    def setDiagnoseMode(self, enabled: bool):
        return self.executeFunction(
            "setDiagnoseMode",
            {"system": {"sys": {"diagnose_mode": "on" if enabled else "off"}}},
        )

    # enabled is boolean, time is string like "03:00", random_range is constant in app
    def setFirmwareAutoUpgradeConfig(self, enabled=None, time=None):
        params = {"random_range": 120}
        if enabled is not None:
            params["enabled"] = "on" if enabled else "off"
        if time is not None:
            params["time"] = time

        return self.executeFunction(
            "setFirmwareAutoUpgradeConfig",
            {"auto_upgrade": {"common": params}},
        )

    def getRotationStatus(self):
        return self.executeFunction(
            "getRotationStatus",
            {"image": {"name": ["switch"]}},
        )

    def getLED(self):
        return self.executeFunction(
            "getLedStatus",
            {"led": {"name": ["config"]}},
        )[
            "led"
        ]["config"]

    def getSDCard(self):
        return self.executeFunction(
            "getSdCardStatus",
            {"harddisk_manage": {"table": ["hd_info"]}},
        )["harddisk_manage"]["hd_info"]

    def getRecordPlan(self):
        return self.executeFunction(
            "getRecordPlan",
            {"record_plan": {"name": ["chn1_channel"]}},
        )["record_plan"]["chn1_channel"]

    def setRecordPlan(
        self,
        enabled,
        sunday=None,
        monday=None,
        tuesday=None,
        wednesday=None,
        thursday=None,
        friday=None,
        saturday=None,
    ):
        """
        Example day object - list with explanation:
        [
            "0000-0700:1", # Record continuously from 00:00 to 07:00 (note the :1)
            "0700-0900:2", # Record on motion from 07:00 to 09:00 (note the :2)
            "0900-1100:1", # Record continuously from 09:00 to 11:00
            "1100-1200:2", # Record on motion from 11:00 to 12:00
            "1200-1500:1", # Record continuously from 12:00 to 15:00
                        # No recording from 15:00 to 17:00 (note the missing time between 15 to 17 in array)
            "1700-2400:1", # Record continuously from 17:00 to 24:00
        ]
        """
        recordPlan = {"enabled": "on" if enabled else "off"}

        if sunday is not None and type(sunday) is list:
            recordPlan["sunday"] = json.dumps(sunday)
        if monday is not None and type(monday) is list:
            recordPlan["monday"] = json.dumps(monday)
        if tuesday is not None and type(tuesday) is list:
            recordPlan["tuesday"] = json.dumps(tuesday)
        if wednesday is not None and type(wednesday) is list:
            recordPlan["wednesday"] = json.dumps(wednesday)
        if thursday is not None and type(thursday) is list:
            recordPlan["thursday"] = json.dumps(thursday)
        if friday is not None and type(friday) is list:
            recordPlan["friday"] = json.dumps(friday)
        if saturday is not None and type(saturday) is list:
            recordPlan["saturday"] = json.dumps(saturday)

        return self.executeFunction(
            "setRecordPlan",
            {"record_plan": {"chn1_channel": recordPlan}},
        )

    def getCircularRecordingConfig(self):
        return self.executeFunction(
            "getCircularRecordingConfig",
            {"harddisk_manage": {"name": "harddisk"}},
        )["harddisk_manage"]["harddisk"]

    def setCircularRecordingConfig(self, enabled):
        return self.executeFunction(
            "setCircularRecordingConfig",
            {"harddisk_manage": {"harddisk": {"loop": "on" if enabled else "off"}}},
        )

    def getAutoTrackTarget(self):
        return self.executeFunction(
            "getTargetTrackConfig", {"target_track": {"name": ["target_track_info"]}}
        )["target_track"]["target_track_info"]

    # does not work for child devices, function discovery needed
    def getAudioSpec(self):
        return self.performRequest(
            {
                "get": {
                    "audio_capability": {
                        "name": ["device_speaker", "device_microphone"]
                    }
                }
            }
        )

    def getAudioConfig(self):
        return self.executeFunction(
            "getAudioConfig",
            {"audio_config": {"name": ["speaker", "microphone", "record_audio"]}},
        )

    def setRecordAudio(self, enabled: bool):
        return self.executeFunction(
            "setRecordAudio",
            {"audio_config": {"record_audio": {"enabled": "on" if enabled else "off"}}},
        )

    def setSpeakerVolume(self, volume):
        return self.executeFunction(
            "setSpeakerVolume",
            {"audio_config": {"speaker": {"volume": volume}}},
        )

    def setMicrophone(self, volume=None, mute=None, noise_cancelling=None):
        params = {"audio_config": {"microphone": {}}}
        if volume is not None:
            params["audio_config"]["microphone"]["volume"] = volume
        if mute is not None:
            params["audio_config"]["microphone"]["mute"] = "on" if mute else "off"
        if noise_cancelling is not None:
            params["audio_config"]["microphone"]["noise_cancelling"] = (
                "on" if noise_cancelling else "off"
            )
        return self.executeFunction(
            "setMicrophoneVolume",
            params,
        )

    # does not work for child devices, function discovery needed
    def getVhttpd(self):
        return self.performRequest({"get": {"cet": {"name": ["vhttpd"]}}})

    def getWhitelampStatus(self):
        return self.executeFunction(
            "getWhitelampStatus", {"image": {"get_wtl_status": ["null"]}}
        )

    def getFloodlightStatus(self):
        return self.executeFunction(
            "getFloodlightStatus", {"floodlight": {"get_floodlight_status": ""}}
        )

    def manualFloodlightOp(self, status: bool):
        return self.executeFunction(
            "manualFloodlightOp",
            {
                "floodlight": {
                    "manual_floodlight_op": {"action": "start" if status else "stop"}
                }
            },
        )

    def getFloodlightConfig(self):
        return self.executeFunction(
            "getFloodlightConfig", {"floodlight": {"name": "config"}}
        )["floodlight"]["config"]

    def setFloodlightConfig(
        self,
        autoOffEnabled: bool = None,
        scheduleMode=None,
        endTime=None,
        imgDetTriEnabled: bool = None,
        intensityLevel: int = None,
        scheduleEnabled: bool = None,
        manualDuration: int = None,
        startTime: int = None,
        sunriseOffset: int = None,
        sunsetOffset: int = None,
        triggerDuration: int = None,
    ):
        config = {}
        if scheduleMode is not None:
            config["schedule_mode"] = scheduleMode
        if autoOffEnabled is not None:
            config["auto_off_enabled"] = "on" if autoOffEnabled else "off"
        if endTime is not None:
            config["end_time"] = endTime
        if imgDetTriEnabled is not None:
            config["img_det_tri_enabled"] = imgDetTriEnabled
        if intensityLevel is not None:
            config["intensity_level"] = str(intensityLevel)
        if scheduleEnabled is not None:
            config["schedule_enabled"] = "on" if scheduleEnabled else "off"
        if manualDuration is not None:
            config["manual_duration"] = str(manualDuration)
        if startTime is not None:
            config["start_time"] = str(startTime)
        if sunriseOffset is not None:
            config["sunrise_offset"] = str(sunriseOffset)
        if sunsetOffset is not None:
            config["sunset_offset"] = str(sunsetOffset)
        if triggerDuration is not None:
            config["trigger_duration"] = str(triggerDuration)
        return self.executeFunction(
            "setFloodlightConfig",
            {"floodlight": {"config": config}},
        )

    def getFloodlightCapability(self):
        return self.executeFunction(
            "getFloodlightCapability", {"floodlight": {"name": "capability"}}
        )["floodlight"]["capability"]

    def getPirDetCapability(self):
        return self.executeFunction(
            "getPirDetCapability", {"pir_detection": {"name": "pir_capability"}}
        )["pir_detection"]["pir_capability"]

    def getPirDetConfig(self):
        return self.executeFunction(
            "getPirDetConfig", {"pir_detection": {"name": "pir_det"}}
        )["pir_detection"]["pir_det"]

    # channels example: ['off', 'on', 'off']
    # sensitivity example: ['10', '10', '10']
    def setPirDetConfig(self, enabled: bool = None, channels=[], sensitivity=[]):
        config = {}
        if enabled is not None:
            config["enabled"] = "on" if enabled else "off"
        if channels:
            config["channel_enabled"] = channels
        if sensitivity:
            config["sensitivity"] = sensitivity
        return self.executeFunction(
            "setPirDetConfig", {"pir_detection": {"pir_det": config}}
        )

    def reverseWhitelampStatus(self):
        return self.executeFunction(
            "reverseWhitelampStatus", {"image": {"reverse_wtl_status": ["null"]}}
        )

    def playAlarm(self, alarmDuration, alarmType, alarmVolume):
        return self.executeFunction(
            "play_alarm",
            {
                "alarm_duration": int(alarmDuration),
                "alarm_type": str(alarmType),
                "alarm_volume": str(alarmVolume),
            },
        )

    def getBasicInfo(self):
        if self.isKLAP:
            return self.executeFunction("get_device_info", None)
        else:
            return self.executeFunction(
                "getDeviceInfo", {"device_info": {"name": ["basic_info"]}}
            )

    def getTime(self):
        if self.isKLAP:
            return self.executeFunction("get_device_time", None)
        else:
            return self.executeFunction(
                "getClockStatus", {"system": {"name": "clock_status"}}
            )

    def getDSTRule(self):
        return self.executeFunction("getDstRule", {"system": {"name": "dst"}})

    # does not work for child devices, function discovery needed
    def getMotorCapability(self):
        return self.performRequest({"get": {"motor": {"name": ["capability"]}}})

    def setPrivacyMode(self, enabled):
        return self.executeFunction(
            "setLensMaskConfig",
            {"lens_mask": {"lens_mask_info": {"enabled": "on" if enabled else "off"}}},
        )

    def getSmartTrackConfig(self):
        return self.executeFunction(
            "getSmartTrackConfig",
            {"smart_track": {"name": "smart_track_info"}},
        )

    def getWhitelampConfig(self):
        return self.executeFunction(
            "getWhitelampConfig",
            {"image": {"name": "switch"}},
        )

    def setWhitelampConfig(self, forceTime=False, intensityLevel=False):
        params = {"image": {"switch": {}}}
        if forceTime is not False:
            params["image"]["switch"]["wtl_force_time"] = str(forceTime)
        if intensityLevel is not False:
            params["image"]["switch"]["wtl_intensity_level"] = str(intensityLevel)

        return self.executeFunction(
            "setWhitelampConfig",
            params,
        )

    def getNotificationsEnabled(self):
        params = {"msg_push": {"name": ["chn1_msg_push_info"]}}

        data = self.executeFunction(
            "getMsgPushConfig",
            params,
        )
        return data["msg_push"]["chn1_msg_push_info"]

    def setNotificationsEnabled(
        self, notificationsEnabled=None, richNotificationsEnabled=None
    ):
        params = {"msg_push": {"chn1_msg_push_info": {}}}
        if notificationsEnabled is not None:
            params["msg_push"]["chn1_msg_push_info"]["notification_enabled"] = (
                "off" if notificationsEnabled is False else "on"
            )
        if richNotificationsEnabled is not None:
            params["msg_push"]["chn1_msg_push_info"]["rich_notification_enabled"] = (
                "off" if richNotificationsEnabled is False else "on"
            )

        return self.executeFunction(
            "setMsgPushConfig",
            params,
        )

    def setMediaEncrypt(self, enabled):
        return self.executeFunction(
            "setMediaEncrypt",
            {"cet": {"media_encrypt": {"enabled": "on" if enabled else "off"}}},
        )

    # todo child
    def setAlarm(
        self,
        enabled,
        soundEnabled=True,
        lightEnabled=True,
        alarmVolume=None,
        alarmDuration=None,
        alarmType=None,
    ):
        alarm_mode = []

        # if this is not set the structure is then missing alarm_mode after update, it needs to be there always!
        if not soundEnabled and not lightEnabled:
            raise Exception("You need to use at least sound or light for alarm")

        if soundEnabled:
            if self.childID:
                alarm_mode.append("siren")
            else:
                alarm_mode.append("sound")
        if lightEnabled:
            alarm_mode.append("light")

        if self.childID:
            data = {
                "msg_alarm": {
                    "enabled": "on" if enabled else "off",
                    "alarm_mode": alarm_mode,
                }
            }
            if alarmVolume is not None:
                data["msg_alarm"]["alarm_volume"] = alarmVolume
            if alarmDuration is not None:
                data["msg_alarm"]["alarm_duration"] = alarmDuration
            if alarmType is not None:
                data["msg_alarm"]["alarm_type"] = str(alarmType)
            return self.executeFunction("setAlarmConfig", data)
        else:
            data = {
                "set": {
                    "msg_alarm": {
                        "chn1_msg_alarm_info": {
                            "alarm_type": "0",
                            "enabled": "on" if enabled else "off",
                            "light_type": "0",
                            "alarm_mode": alarm_mode,
                        }
                    },
                }
            }
            if alarmVolume is not None:
                data["msg_alarm"]["chn1_msg_alarm_info"]["alarm_volume"] = alarmVolume
            if alarmDuration is not None:
                data["msg_alarm"]["chn1_msg_alarm_info"][
                    "alarm_duration"
                ] = alarmDuration
            if alarmType is not None:
                data["msg_alarm"]["chn1_msg_alarm_info"]["alarm_type"] = str(alarmType)
            return self.performRequest(data)

    # todo child
    def moveMotor(self, x, y):
        return self.performRequest(
            {"do": {"motor": {"move": {"x_coord": str(x), "y_coord": str(y)}}}}
        )

    # todo child
    def moveMotorStep(self, angle):
        if not (0 <= angle < 360):
            raise Exception("Angle must be in a range 0 <= angle < 360")

        return self.performRequest(
            {"do": {"motor": {"movestep": {"direction": str(angle)}}}}
        )

    def moveMotorClockWise(self):
        return self.moveMotorStep(0)

    def moveMotorCounterClockWise(self):
        return self.moveMotorStep(180)

    def moveMotorVertical(self):
        return self.moveMotorStep(90)

    def moveMotorHorizontal(self):
        return self.moveMotorStep(270)

    # todo child
    def calibrateMotor(self):
        return self.performRequest({"do": {"motor": {"manual_cali": ""}}})

    def format(self):
        return self.executeFunction(
            "formatSdCard", {"harddisk_manage": {"format_hd": "1"}}
        )  # pragma: no cover

    def setLEDEnabled(self, enabled):
        if self.isKLAP:
            return self.executeFunction(
                "set_led_off",
                {"led_off": 0 if enabled else 1},
            )
        else:
            return self.executeFunction(
                "setLedStatus",
                {"led": {"config": {"enabled": "on" if enabled else "off"}}},
            )

    def getUserID(self, forceReload=False):
        if not self.userID or forceReload is True:
            response = self.userID = self.performRequest(
                {
                    "multipleRequest": {
                        "requests": [
                            {
                                "method": "getUserID",
                                "params": {"system": {"get_user_id": "null"}},
                            }
                        ]
                    }
                }
            )["result"]["responses"][0]["result"]
            if "error_code" not in response or response["error_code"] == 0:
                self.userID = response["user_id"]
            else:
                if "error_code" in response and response["error_code"] == -71101:
                    self.userID = self.getUserID()
                else:
                    raise Exception(response)
        return self.userID

    def getRecordingsList(self, start_date="20000101", end_date=None):
        if end_date is None:
            end_date = datetime.today().strftime("%Y%m%d")
        result = self.executeFunction(
            "searchDateWithVideo",
            {
                "playback": {
                    "search_year_utility": {
                        "channel": [0],
                        "end_date": end_date,
                        "start_date": start_date,
                    }
                }
            },
        )
        if "playback" not in result:
            raise Exception("Video playback is not supported by this camera")
        return result["playback"]["search_results"]

    def getRecordingsUTC(
        self, start_time, end_time, start_index=0, end_index=999999999
    ):
        try:
            result = self.executeFunction(
                "searchVideoWithUTC",
                {
                    "playback": {
                        "search_video_with_utc": {
                            "channel": 0,
                            "end_time": end_time,
                            "end_index": end_index,
                            "id": self.getUserID(),
                            "start_index": start_index,
                            "start_time": start_time,
                        }
                    }
                },
            )

            if "playback" not in result:
                raise Exception("Video playback is not supported by this camera")

            return result["playback"]["search_video_results"]
        except Exception as err:
            # user ID expired, get a new one
            if ERROR_CODES["-71103"] in str(err):
                self.getUserID(True)
                return self.getRecordingsUTC(
                    start_time, end_time, start_index, end_index
                )

    def getRecordings(self, date, start_index=0, end_index=999999999):
        if self.childID is not None:
            date_object = datetime.strptime(date, "%Y%m%d")
            start_time = int(date_object.timestamp())
            end_time = int(
                (date_object + timedelta(hours=23, minutes=59, seconds=59)).timestamp()
            )
            return self.getRecordingsUTC(start_time, end_time, start_index, end_index)
        try:
            result = self.executeFunction(
                "searchVideoOfDay",
                {
                    "playback": {
                        "search_video_utility": {
                            "channel": 0,
                            "date": date,
                            "end_index": end_index,
                            "id": self.getUserID(),
                            "start_index": start_index,
                        }
                    }
                },
            )
            if "playback" not in result:
                raise Exception("Video playback is not supported by this camera")
            return result["playback"]["search_video_results"]
        except Exception as err:
            # user ID expired, get a new one
            if ERROR_CODES["-71103"] in str(err):
                self.getUserID(True)
                return self.getRecordings(date, start_index, end_index)

    # does not work for child devices, function discovery needed
    def getCommonImage(self):
        warn("Prefer to use a specific value getter", DeprecationWarning, stacklevel=2)
        return self.performRequest({"get": {"image": {"name": "common"}}})

    def __getSensitivityNumber(self, sensitivity):
        if isinstance(sensitivity, int) or (
            isinstance(sensitivity, str) and sensitivity.isnumeric()
        ):
            sensitivityInt = int(sensitivity)
            if sensitivityInt >= 0 and sensitivityInt <= 100:
                return str(sensitivityInt)
            else:
                raise Exception("Invalid sensitivity, can be between 0 and 100.")
        else:
            if sensitivity == "high":
                return "80"
            elif sensitivity == "normal":
                return "50"
            elif sensitivity == "low":
                return "20"
            else:
                raise Exception("Invalid sensitivity, can be low, normal or high")

    def getMotionDetection(self):
        return self.executeFunction(
            "getDetectionConfig",
            {"motion_detection": {"name": ["motion_det"]}},
        )["motion_detection"]["motion_det"]

    def setMotionDetection(self, enabled=None, sensitivity=False):
        data = {
            "motion_detection": {"motion_det": {}},
        }
        if enabled is not None:
            data["motion_detection"]["motion_det"]["enabled"] = (
                "on" if enabled else "off"
            )

        if sensitivity:
            data["motion_detection"]["motion_det"]["digital_sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )
        # child devices always need digital_sensitivity setting
        if (
            self.childID
            and "digital_sensitivity" not in data["motion_detection"]["motion_det"]
        ):
            currentData = self.getMotionDetection()
            data["motion_detection"]["motion_det"]["digital_sensitivity"] = currentData[
                "digital_sensitivity"
            ]
        return self.executeFunction("setDetectionConfig", data)

    def getPersonDetection(self):
        return self.executeFunction(
            "getPersonDetectionConfig",
            {"people_detection": {"name": ["detection"]}},
        )["people_detection"]["detection"]

    def setPersonDetection(self, enabled, sensitivity=False):
        data = {
            "people_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["people_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )
        return self.executeFunction("setPersonDetectionConfig", data)

    def getVehicleDetection(self):
        return self.executeFunction(
            "getVehicleDetectionConfig",
            {"vehicle_detection": {"name": ["detection"]}},
        )["vehicle_detection"]["detection"]

    def setVehicleDetection(self, enabled, sensitivity=False):
        data = {
            "vehicle_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["vehicle_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )
        return self.executeFunction("setVehicleDetectionConfig", data)

    def getPetDetection(self):
        return self.executeFunction(
            "getPetDetectionConfig",
            {"pet_detection": {"name": ["detection"]}},
        )["pet_detection"]["detection"]

    def getPackageDetection(self):
        return self.executeFunction(
            "getPackageDetectionConfig",
            {"package_detection": {"name": ["detection"]}},
        )["package_detection"]["detection"]

    def setPetDetection(self, enabled, sensitivity=False):
        data = {"pet_detection": {"detection": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            data["pet_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )

        return self.executeFunction("setPetDetectionConfig", data)

    def setPackageDetection(self, enabled, sensitivity=False):
        data = {
            "package_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            if int(sensitivity) < 1 or int(sensitivity) > 100:
                raise Exception("Sensitivity has to be between 1 and 100.")
            data["package_detection"]["detection"]["sensitivity"] = sensitivity

        return self.executeFunction("setPackageDetectionConfig", data)

    def testUsrDefAudio(self, id: int, enabled: bool, force: int = 1):
        if enabled:
            data = {
                "msg_alarm": {
                    "test_usr_def_audio": {"force": str(force), "id": str(id)}
                }
            }
        else:
            data = {"msg_alarm": {"test_usr_def_audio": {"action": "stop"}}}

        return self.executeFunction("testUsrDefAudio", data)

    def getAlertEventType(self):
        return self.executeFunction(
            "getAlertEventType",
            {"msg_alarm": {"table": "msg_alarm_type"}},
        )["msg_alarm"]["msg_alarm_type"]

    def setAlertEventType(self, name: str, enabled: bool):
        availableAlertEventTypes = self.getAlertEventType()
        eventTypes = []
        typeFound = False
        for eventType in availableAlertEventTypes:
            if name == eventType["name"]:
                eventTypes.append(
                    {"name": eventType["name"], "enabled": "on" if enabled else "off"}
                )
                typeFound = True
            else:
                eventTypes.append(
                    {"name": eventType["name"], "enabled": eventType["enabled"]}
                )
        if typeFound is False:
            raise Exception(f"Invalid alert name. {name} is not supported on camera.")
        data = {"msg_alarm": {"msg_alarm_type": eventTypes}}

        return self.executeFunction("setAlertEventType", data)

    def getBarkDetection(self):
        return self.executeFunction(
            "getBarkDetectionConfig",
            {"bark_detection": {"name": ["detection"]}},
        )["bark_detection"]["detection"]

    def getMeowDetection(self):
        return self.executeFunction(
            "getMeowDetectionConfig",
            {"meow_detection": {"name": ["detection"]}},
        )["meow_detection"]["detection"]

    def setBarkDetection(self, enabled, sensitivity=False):
        data = {
            "bark_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["bark_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )

        return self.executeFunction("setBarkDetectionConfig", data)

    def setMeowDetection(self, enabled, sensitivity=False):
        data = {
            "meow_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["meow_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )

        return self.executeFunction("setMeowDetectionConfig", data)

    def getGlassBreakDetection(self):
        return self.executeFunction(
            "getGlassDetectionConfig",
            {"glass_detection": {"name": ["detection"]}},
        )["glass_detection"]["detection"]

    def setGlassBreakDetection(self, enabled, sensitivity=False):
        data = {
            "glass_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["glass_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )

        return self.executeFunction("setGlassDetectionConfig", data)

    def getTamperDetection(self):
        return self.executeFunction(
            "getTamperDetectionConfig",
            {"tamper_detection": {"name": "tamper_det"}},
        )["tamper_detection"]["tamper_det"]

    def setTamperDetection(self, enabled, sensitivity=False):
        data = {
            "tamper_detection": {"tamper_det": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            if sensitivity not in ["high", "normal", "low"]:
                raise Exception("Invalid sensitivity, can be low, normal or high")
            if sensitivity == "normal":
                sensitivity = "medium"
            data["tamper_detection"]["tamper_det"]["sensitivity"] = sensitivity

        return self.executeFunction("setTamperDetectionConfig", data)

    def getBabyCryDetection(self):
        return self.executeFunction(
            "getBCDConfig",
            {"sound_detection": {"name": ["bcd"]}},
        )["sound_detection"]["bcd"]

    def getCruise(self):
        data = self.executeFunction(
            "getPatrolAction", {"patrol": {"get_patrol_action": {}}}
        )
        return data

    def setBabyCryDetection(self, enabled, sensitivity=False):
        data = {"sound_detection": {"bcd": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            if sensitivity not in ["high", "normal", "low"]:
                raise Exception("Invalid sensitivity, can be low, normal or high")
            if sensitivity == "normal":
                sensitivity = "medium"
            data["sound_detection"]["bcd"]["sensitivity"] = sensitivity

        return self.executeFunction("setBCDConfig", data)

    def setAutoTrackTarget(self, enabled):
        return self.executeFunction(
            "setTargetTrackConfig",
            {
                "target_track": {
                    "target_track_info": {"enabled": "on" if enabled else "off"}
                }
            },
        )

    def setSmartTrackConfig(self, type: str, enabled: bool):
        return self.executeFunction(
            "setSmartTrackConfig",
            {
                "smart_track": {
                    "smart_track_info": {
                        type: "on" if enabled else "off",
                    }
                }
            },
        )

    def setCruise(self, enabled, coord=False, retry=False):
        if coord not in ["x", "y"] and coord is not False:
            raise Exception("Invalid coord parameter. Can be 'x' or 'y'.")
        if enabled and coord is not False:
            return self.executeFunction(
                "cruiseMove",
                {"motor": {"cruise": {"coord": coord}}},
                retry=retry,
            )
        else:
            return self.executeFunction(
                "cruiseStop",
                {"motor": {"cruise_stop": {}}},
                retry=retry,
            )

    def reboot(self, delay=None):
        if self.isKLAP:
            if delay is None:
                delay = 1
            return self.executeFunction("device_reboot", {"delay": delay})
        else:
            return self.executeFunction("rebootDevice", {"system": {"reboot": "null"}})

    def processPresetsResponse(self, response):
        return {
            id: response["preset"]["preset"]["name"][key]
            for key, id in enumerate(response["preset"]["preset"]["id"])
        }

    def getPresets(self):
        data = self.executeFunction("getPresetConfig", {"preset": {"name": ["preset"]}})
        self.presets = self.processPresetsResponse(data)
        return self.presets

    def savePreset(self, name):
        self.executeFunction(
            "addMotorPostion",  # yes, there is a typo in function name
            {"preset": {"set_preset": {"name": str(name), "save_ptz": "1"}}},
        )
        self.getPresets()
        return True

    def deletePreset(self, presetID, retry=False):
        if not str(presetID) in self.presets:
            if retry is False:
                self.getPresets()
                return self.deletePreset(presetID, True)
            else:
                raise Exception("Preset {} is not set in the app".format(str(presetID)))

        self.executeFunction(
            "deletePreset", {"preset": {"remove_preset": {"id": [str(presetID)]}}}
        )
        self.getPresets()
        return True

    def setPreset(self, presetID, retry=False):
        if not str(presetID) in self.presets:
            if retry is False:
                self.getPresets()
                return self.setPreset(presetID, True)
            else:
                raise Exception("Preset {} is not set in the app".format(str(presetID)))
        return self.executeFunction(
            "motorMoveToPreset", {"preset": {"goto_preset": {"id": str(presetID)}}}
        )

    # Switches

    def __getImageSwitch(self, switch: str) -> str:
        data = self.executeFunction("getLdc", {"image": {"name": ["switch"]}})
        switches = data["image"]["switch"]
        if switch not in switches:
            raise Exception("Switch {} is not supported by this camera".format(switch))
        return switches[switch]

    def __setImageSwitch(self, switch: str, value: str):
        return self.executeFunction("setLdc", {"image": {"switch": {switch: value}}})

    def getLensDistortionCorrection(self):
        return self.__getImageSwitch("ldc") == "on"

    def setLensDistortionCorrection(self, enable):
        return self.__setImageSwitch("ldc", "on" if enable else "off")

    def getDayNightMode(self) -> str:
        if self.childID:
            rawValue = self.getNightVisionModeConfig()["image"]["switch"][
                "night_vision_mode"
            ]
            if rawValue == "inf_night_vision":
                return "on"
            elif rawValue == "wtl_night_vision":
                return "off"
            elif rawValue == "md_night_vision":
                return "auto"
        else:
            return self.__getImageCommon("inf_type")

    def setDayNightMode(self, mode):
        allowed_modes = ["off", "on", "auto"]
        if mode not in allowed_modes:
            raise Exception("Day night mode must be one of {}".format(allowed_modes))
        if self.childID:
            if mode == "on":
                return self.setNightVisionModeConfig("inf_night_vision")
            elif mode == "off":
                return self.setNightVisionModeConfig("wtl_night_vision")
            elif mode == "auto":
                return self.setNightVisionModeConfig("md_night_vision")
        else:
            return self.__setImageCommon("inf_type", mode)

    def getNightVisionModeConfig(self):
        return self.executeFunction(
            "getNightVisionModeConfig", {"image": {"name": "switch"}}
        )

    def getNightVisionCapability(self):
        return self.executeFunction(
            "getNightVisionCapability",
            {"image_capability": {"name": ["supplement_lamp"]}},
        )

    def setNightVisionModeConfig(self, mode):
        return self.executeFunction(
            "setNightVisionModeConfig",
            {"image": {"switch": {"night_vision_mode": mode}}},
        )

    def getImageFlipVertical(self):
        if self.childID:
            return self.getRotationStatus()["image"]["switch"]["flip_type"] == "center"
        else:
            return self.__getImageSwitch("flip_type") == "center"

    def setImageFlipVertical(self, enable):
        if self.childID:
            return self.setRotationStatus("center" if enable else "off")
        else:
            return self.__setImageSwitch("flip_type", "center" if enable else "off")

    def setRotationStatus(self, flip_type):
        return self.executeFunction(
            "setRotationStatus",
            {"image": {"switch": {"flip_type": flip_type}}},
        )

    def getForceWhitelampState(self) -> bool:
        return self.__getImageSwitch("force_wtl_state") == "on"

    def setForceWhitelampState(self, enable: bool):
        return self.__setImageSwitch("force_wtl_state", "on" if enable else "off")

    # Common

    def __getImageCommon(self, field: str) -> str:
        data = self.executeFunction(
            "getLightFrequencyInfo", {"image": {"name": "common"}}
        )
        if "common" not in data["image"]:
            raise Exception("__getImageCommon is not supported by this camera")
        fields = data["image"]["common"]
        if field not in fields:
            raise Exception("Field {} is not supported by this camera".format(field))
        return fields[field]

    def __setImageCommon(self, field: str, value: str):
        return self.executeFunction(
            "setLightFrequencyInfo", {"image": {"common": {field: value}}}
        )

    def getLightFrequencyMode(self) -> str:
        return self.__getImageCommon("light_freq_mode")

    def setLightFrequencyMode(self, mode):
        # todo: auto does not work on some child cameras?
        allowed_modes = ["auto", "50", "60"]
        if mode not in allowed_modes:
            raise Exception(
                "Light frequency mode must be one of {}".format(allowed_modes)
            )
        return self.__setImageCommon("light_freq_mode", mode)

    # does not work for child devices, function discovery needed
    def startManualAlarm(self):
        return self.performRequest(
            {
                "do": {"msg_alarm": {"manual_msg_alarm": {"action": "start"}}},
            }
        )

    # does not work for child devices, function discovery needed
    def stopManualAlarm(self):
        return self.performRequest(
            {
                "do": {"msg_alarm": {"manual_msg_alarm": {"action": "stop"}}},
            }
        )

    def getDeviceIpAddress(self):
        return self.executeFunction(
            "getDeviceIpAddress", {"network": {"name": ["wan"]}}
        )["network"]["wan"]

    def getChimeRingPlan(self):
        return self.executeFunction(
            "getChimeRingPlan", {"chime_ring_plan": {"name": "chn1_chime_ring_plan"}}
        )

    def getChimeAlarmConfigure(self, macAddress):
        return self.executeFunction("get_chime_alarm_configure", {"mac": macAddress})

    def getSupportAlarmTypeList(self):
        return self.executeFunction("get_support_alarm_type_list", None)

    def setChimeAlarmConfigure(
        self, macAddress, enabled=None, type=None, volume=None, duration=None
    ):
        if duration is not None and (duration < 5 or duration > 30) and duration != 0:
            raise Exception("Duration has to be between 5 and 30, or 0.")
        if volume is not None and (volume < 1 or volume > 15):
            raise Exception("Volume has to be between 1 and 15.")
        params = {"mac": macAddress}
        if enabled is not None:
            params["on_off"] = 1 if enabled else 0
        if type is not None:
            params["type"] = str(type)
        if volume is not None:
            params["volume"] = str(volume)
        if duration is not None:
            params["duration"] = int(duration)
        return self.executeFunction("set_chime_alarm_configure", params)

    def getBatteryStatus(self):
        return self.executeFunction("getBatteryStatus", {"battery": {"name": "status"}})

    def getBatteryPowerSave(self):
        return self.executeFunction(
            "getBatteryPowerSave", {"battery": {"name": "power_save"}}
        )

    def getBatteryOperatingMode(self):
        return self.executeFunction(
            "getBatteryOperatingMode", {"battery": {"name": "operating"}}
        )

    def getBatteryOperatingModeParam(self):
        return self.executeFunction(
            "getBatteryOperatingModeParam",
            {"battery": {"name": "operating_mode_param"}},
        )

    def getChargingMode(self):
        return self.executeFunction(
            "getChargingMode", {"battery": {"name": "charging_mode"}}
        )

    def getPowerMode(self):
        return self.executeFunction("getPowerMode", {"battery": {"name": "power"}})

    def getBatteryStatistic(self):
        return self.executeFunction(
            "getBatteryStatistic", {"battery": {"statistic": {"days": 30}}}
        )

    def getBatteryConfig(self):
        return self.executeFunction("getBatteryConfig", {"battery": {"name": "config"}})

    def getBatteryCapability(self):
        return self.executeFunction(
            "getBatteryCapability", {"battery": {"name": "capability"}}
        )

    def getPirSensitivity(self):
        return self.executeFunction("getPirSensitivity", {"pir": {"name": "config"}})

    @staticmethod
    def getErrorMessage(errorCode):
        if str(errorCode) in ERROR_CODES:
            return str(ERROR_CODES[str(errorCode)])
        else:
            return str(errorCode)

    def getFirmwareUpdateStatus(self):
        return self.executeFunction(
            "getFirmwareUpdateStatus", {"cloud_config": {"name": "upgrade_status"}}
        )

    def isUpdateAvailable(self):
        return self.performRequest(
            {
                "multipleRequest": {
                    "requests": [
                        {
                            "method": "checkFirmwareVersionByCloud",
                            "params": {"cloud_config": {"check_fw_version": "null"}},
                        },
                        {
                            "method": "getCloudConfig",
                            "params": {"cloud_config": {"name": ["upgrade_info"]}},
                        },
                    ]
                }
            }
        )

    def startFirmwareUpgrade(self):
        try:
            self.performRequest({"do": {"cloud_config": {"fw_download": "null"}}})
        except Exception:
            raise Exception("No new firmware available.")

    def playQuickResponse(self, id):
        return self.executeFunction(
            "playQuickResp",
            {"quick_response": {"play_quick_resp_audio": {"id": id, "force": "force"}}},
        )

    def getQuickResponseList(self):
        return self.executeFunction(
            "getQuickRespList",
            {"quick_response": {}},
        )

    # Used for purposes of HomeAssistant-Tapo-Control
    # Uses method names from https://md.depau.eu/s/r1Ys_oWoP
    def getMost(self, omit_methods=[]):
        if self.deviceType == "SMART.TAPOCHIME":
            requestData = {
                "multipleRequest": {
                    "requests": [
                        {
                            "method": "get_device_info",
                        },
                        {"method": "get_pair_list"},
                        {"method": "get_support_alarm_type_list"},
                        {"method": "get_device_time"},
                    ]
                }
            }

            for macAddress in self.pairList["mac_list"]:
                requestData["multipleRequest"]["requests"].append(
                    {
                        "method": "get_chime_alarm_configure",
                        "params": {"mac": macAddress},
                    }
                )
        else:
            requestData = {
                "multipleRequest": {
                    "requests": [
                        {
                            "method": "getDiagnoseMode",
                            "params": {"system": {"name": "sys"}},
                        },
                        {
                            "method": "getCoverConfig",
                            "params": {"cover": {"name": ["cover"]}},
                        },
                        {
                            "method": "getCoverConfig",
                            "params": {"cover": {"table": ["region_info"]}},
                        },
                        {
                            "method": "getSmartTrackConfig",
                            "params": {"smart_track": {"name": "smart_track_info"}},
                        },
                        {
                            "method": "getDeviceIpAddress",
                            "params": {"network": {"name": ["wan"]}},
                        },
                        {
                            "method": "getFloodlightStatus",
                            "params": {"floodlight": {"get_floodlight_status": ""}},
                        },
                        {
                            "method": "getFloodlightConfig",
                            "params": {"floodlight": {"name": "config"}},
                        },
                        {
                            "method": "getFloodlightCapability",
                            "params": {"floodlight": {"name": "capability"}},
                        },
                        {
                            "method": "getPirDetCapability",
                            "params": {"pir_detection": {"name": "pir_capability"}},
                        },
                        {
                            "method": "getPirDetConfig",
                            "params": {"pir_detection": {"name": "pir_det"}},
                        },
                        {
                            "method": "getAlertEventType",
                            "params": {"msg_alarm": {"table": "msg_alarm_type"}},
                        },
                        {
                            "method": "getDstRule",
                            "params": {"system": {"name": "dst"}},
                        },
                        {
                            "method": "getClockStatus",
                            "params": {"system": {"name": "clock_status"}},
                        },
                        {
                            "method": "getTimezone",
                            "params": {"system": {"name": ["basic"]}},
                        },
                        {
                            "method": "getAlertTypeList",
                            "params": {"msg_alarm": {"name": "alert_type"}},
                        },
                        {
                            "method": "getNightVisionCapability",
                            "params": {
                                "image_capability": {"name": ["supplement_lamp"]}
                            },
                        },
                        {
                            "method": "getDeviceInfo",
                            "params": {"device_info": {"name": ["basic_info"]}},
                        },
                        {
                            "method": "getDetectionConfig",
                            "params": {"motion_detection": {"name": ["motion_det"]}},
                        },
                        {
                            "method": "getPersonDetectionConfig",
                            "params": {"people_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getVehicleDetectionConfig",
                            "params": {"vehicle_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getBCDConfig",
                            "params": {"sound_detection": {"name": ["bcd"]}},
                        },
                        {
                            "method": "getPetDetectionConfig",
                            "params": {"pet_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getPackageDetectionConfig",
                            "params": {"package_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getBarkDetectionConfig",
                            "params": {"bark_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getMeowDetectionConfig",
                            "params": {"meow_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getGlassDetectionConfig",
                            "params": {"glass_detection": {"name": ["detection"]}},
                        },
                        {
                            "method": "getTamperDetectionConfig",
                            "params": {"tamper_detection": {"name": "tamper_det"}},
                        },
                        {
                            "method": "getLensMaskConfig",
                            "params": {"lens_mask": {"name": ["lens_mask_info"]}},
                        },
                        {
                            "method": "getLdc",
                            "params": {"image": {"name": ["switch", "common"]}},
                        },
                        {
                            "method": "getLastAlarmInfo",
                            "params": {"msg_alarm": {"name": ["chn1_msg_alarm_info"]}},
                        },
                        {
                            "method": "getLedStatus",
                            "params": {"led": {"name": ["config"]}},
                        },
                        {
                            "method": "getTargetTrackConfig",
                            "params": {"target_track": {"name": ["target_track_info"]}},
                        },
                        {
                            "method": "getPresetConfig",
                            "params": {"preset": {"name": ["preset"]}},
                        },
                        {
                            "method": "getFirmwareUpdateStatus",
                            "params": {"cloud_config": {"name": "upgrade_status"}},
                        },
                        {
                            "method": "getMediaEncrypt",
                            "params": {"cet": {"name": ["media_encrypt"]}},
                        },
                        {
                            "method": "getConnectionType",
                            "params": {"network": {"get_connection_type": []}},
                        },
                        {"method": "getAlarmConfig", "params": {"msg_alarm": {}}},
                        {"method": "getAlarmPlan", "params": {"msg_alarm_plan": {}}},
                        {"method": "getSirenTypeList", "params": {"msg_alarm": {}}},
                        {"method": "getSirenTypeList", "params": {"siren": {}}},
                        {"method": "getSirenConfig", "params": {"siren": {}}},
                        {
                            "method": "getAlertConfig",
                            "params": {
                                "msg_alarm": {
                                    "name": ["chn1_msg_alarm_info", "capability"],
                                    "table": ["usr_def_audio"],
                                }
                            },
                        },
                        {
                            "method": "getAlertConfig",
                            "params": {
                                "msg_alarm": {
                                    "name": ["chn1_msg_alarm_info"],
                                    "table": ["usr_def_audio"],
                                }
                            },
                        },
                        {"method": "getLightTypeList", "params": {"msg_alarm": {}}},
                        {"method": "getSirenStatus", "params": {"msg_alarm": {}}},
                        {"method": "getSirenStatus", "params": {"siren": {}}},
                        {
                            "method": "getLightFrequencyInfo",
                            "params": {"image": {"name": "common"}},
                        },
                        {
                            "method": "getLightFrequencyCapability",
                            "params": {"image": {"name": "common"}},
                        },
                        {
                            "method": "getChildDeviceList",
                            "params": {"childControl": {"start_index": 0}},
                        },
                        {
                            "method": "getRotationStatus",
                            "params": {"image": {"name": ["switch"]}},
                        },
                        {
                            "method": "getNightVisionModeConfig",
                            "params": {"image": {"name": "switch"}},
                        },
                        {
                            "method": "getWhitelampStatus",
                            "params": {"image": {"get_wtl_status": ["null"]}},
                        },
                        {
                            "method": "getWhitelampConfig",
                            "params": {"image": {"name": "switch"}},
                        },
                        {
                            "method": "getMsgPushConfig",
                            "params": {"msg_push": {"name": ["chn1_msg_push_info"]}},
                        },
                        {
                            "method": "getSdCardStatus",
                            "params": {"harddisk_manage": {"table": ["hd_info"]}},
                        },
                        {
                            "method": "getCircularRecordingConfig",
                            "params": {"harddisk_manage": {"name": "harddisk"}},
                        },
                        {
                            "method": "getRecordPlan",
                            "params": {"record_plan": {"name": ["chn1_channel"]}},
                        },
                        {
                            "method": "getAudioConfig",
                            "params": {
                                "audio_config": {
                                    "name": ["speaker", "microphone", "record_audio"]
                                },
                            },
                        },
                        {
                            "method": "getFirmwareAutoUpgradeConfig",
                            "params": {
                                "auto_upgrade": {"name": ["common"]},
                            },
                        },
                        {
                            "method": "getVideoQualities",
                            "params": {"video": {"name": ["main"]}},
                        },
                        {
                            "method": "getVideoCapability",
                            "params": {"video_capability": {"name": "main"}},
                        },
                        {
                            "method": "getQuickRespList",
                            "params": {"quick_response": {}},
                        },
                        {
                            "method": "getChimeRingPlan",
                            "params": {
                                "chime_ring_plan": {"name": "chn1_chime_ring_plan"}
                            },
                        },
                        {
                            "method": "getRingStatus",
                            "params": {"ring": {"name": "status"}},
                        },
                        {
                            "method": "getChimeCtrlList",
                            "params": {"chime_ctrl": {"get_paired_device_list": {}}},
                        },
                        {
                            "method": "getBatteryPowerSave",
                            "params": {"battery": {"name": "power_save"}},
                        },
                        {
                            "method": "getBatteryOperatingMode",
                            "params": {"battery": {"name": "operating"}},
                        },
                        {
                            "method": "getBatteryOperatingModeParam",
                            "params": {"battery": {"name": "operating_mode_param"}},
                        },
                        {
                            "method": "getPowerMode",
                            "params": {"battery": {"name": "power"}},
                        },
                        {
                            "method": "getChargingMode",
                            "params": {"battery": {"name": "charging_mode"}},
                        },
                        {
                            "method": "getBatteryStatistic",
                            "params": {"battery": {"statistic": {"days": 30}}},
                        },
                        {
                            "method": "getBatteryConfig",
                            "params": {"battery": {"name": "config"}},
                        },
                        {
                            "method": "getWakeUpConfig",
                            "params": {"wake_up": {"name": "config"}},
                        },
                        {
                            "method": "getBatteryCapability",
                            "params": {"battery": {"name": "capability"}},
                        },
                        {
                            "method": "getHubStorage",
                            "params": {"hub_manage": {"name": "hub_storage_info"}},
                        },
                        {
                            "method": "getPirSensitivity",
                            "params": {"pir": {"name": "config"}},
                        },
                        {
                            "method": "getClipsConfig",
                            "params": {"clips": {"name": "config"}},
                        },
                    ]
                }
            }
        if len(omit_methods) != 0:
            filtered_requests = [
                request
                for request in requestData["multipleRequest"]["requests"]
                if request.get("method") not in omit_methods
            ]
            requestData["multipleRequest"]["requests"] = filtered_requests

        results = self.performRequest(requestData)

        # handle malformed / unexpected response from camera
        if len(requestData["multipleRequest"]["requests"]) != len(
            results["result"]["responses"]
        ):
            if len(omit_methods) == 0:
                # It was found in https://github.com/JurajNyiri/HomeAssistant-Tapo-Control/issues/455
                # that on Tapo hubs with encryption enabled having getAudioConfig results in malformed
                # response, where camera returns invalid json and incorrect number of responses (1)
                # containing all the others. When getAudioConfig is not requested in this function
                # it returns everything as expected.
                return self.getMost(["getAudioConfig"])
            else:
                raise Exception(f"Unexpected camera response: {results}")

        returnData = {}

        # pre-allocate responses due to some devices not returning methods back
        for request in requestData["multipleRequest"]["requests"]:
            if request["method"] in returnData:
                returnData[request["method"]].append(False)
            else:
                returnData[request["method"]] = [False]

        for omittedMethod in omit_methods:
            returnData[omittedMethod] = [False]

        # Fill the False responses with data
        # It was found in https://github.com/JurajNyiri/HomeAssistant-Tapo-Control/pull/559 that hubs respond in
        # a different order than requested, therefore we do not know which response relates to which request
        for result in results["result"]["responses"]:
            if (
                "error_code" in result and result["error_code"] == 0
            ) and "result" in result:
                if result["method"] not in returnData:
                    raise Exception(
                        f"Method {result['method']} was not requested and has been returned. Response: {results}"
                    )
                foundAllocationForResponse = False
                for i in range(len(returnData[result["method"]])):
                    if returnData[result["method"]][i] is False:
                        returnData[result["method"]][i] = result["result"]
                        foundAllocationForResponse = True
                        break
                if not foundAllocationForResponse:
                    raise Exception(
                        f"Method {result['method']} has been returned more times than expected. Response: {results}"
                    )

        if "getPresetConfig" in returnData and len(returnData["getPresetConfig"]) == 1:
            if returnData["getPresetConfig"][0]:
                self.presets = self.processPresetsResponse(
                    returnData["getPresetConfig"][0]
                )
        elif self.deviceType != "SMART.TAPOCHIME":
            raise Exception("Unexpected number of getPresetConfig responses")

        if "get_device_info" in returnData:
            self.basicInfo = returnData["get_device_info"]
        elif "getDeviceInfo" in returnData:
            self.basicInfo = returnData["getDeviceInfo"]

        if "get_pair_list" in returnData:
            self.pairList = returnData["get_pair_list"][0]

        return returnData
