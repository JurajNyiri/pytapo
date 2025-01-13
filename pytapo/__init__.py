#
# Author: See contributors at https://github.com/JurajNyiri/pytapo/graphs/contributors
#
import hashlib
import json
import requests
import base64
import copy

from datetime import datetime
from warnings import warn
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .const import ERROR_CODES, MAX_LOGIN_RETRIES, EncryptionMethod
from .media_stream.session import HttpMediaSession
from .TlsAdapter import TlsAdapter
from .media_stream._utils import (
    generate_nonce,
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
    ):
        self.retryStok = retryStok
        self.redactConfidentialInformation = redactConfidentialInformation
        self.printDebugInformation = printDebugInformation
        self.passwordEncryptionMethod = None
        self.seq = None
        self.host = host
        self.controlPort = controlPort
        self.lsk = None
        self.cnonce = None
        self.ivb = None
        self.user = user
        self.password = password
        self.cloudPassword = cloudPassword
        self.superSecretKey = superSecretKey
        self.stok = False
        self.userID = False
        self.childID = childID
        self.timeCorrection = False
        self.reuseSession = reuseSession
        self.isSecureConnectionCached = None
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
        self.presets = self.isSupportingPresets()
        if not self.presets:
            self.presets = {}

    def isSupportingPresets(self):
        try:
            presets = self.getPresets()
            return presets
        except Exception:
            return False

    def getHostURL(self):
        return "https://{host}/stok={stok}/ds".format(
            host=self.getControlHost(), stok=self.stok
        )

    def getStreamURL(self):
        return "{host}:8800".format(host=self.host)

    def ensureAuthenticated(self):
        if not self.stok:
            return self.refreshStok()
        return True

    def request(self, method, url, **kwargs):
        if self.session is False and self.reuseSession is True:
            self.session = requests.session()
            self.session.mount("https://", TlsAdapter())

        if self.reuseSession is True:
            session = self.session
        else:
            session = requests.session()
            session.mount("https://", TlsAdapter())
        if self.printDebugInformation:
            redactedKwargs = copy.deepcopy(kwargs)
            if self.redactConfidentialInformation:
                if "data" in redactedKwargs:
                    redactedKwargsData = json.loads(redactedKwargs["data"])
                    if "params" in redactedKwargsData:
                        if (
                            "password" in redactedKwargsData["params"]
                            and redactedKwargsData["params"]["password"] != ""
                        ):
                            redactedKwargsData["params"]["password"] = "REDACTED"
                        if (
                            "digest_passwd" in redactedKwargsData["params"]
                            and redactedKwargsData["params"]["digest_passwd"] != ""
                        ):
                            redactedKwargsData["params"]["digest_passwd"] = "REDACTED"
                        if (
                            "cnonce" in redactedKwargsData["params"]
                            and redactedKwargsData["params"]["cnonce"] != ""
                        ):
                            redactedKwargsData["params"]["cnonce"] = "REDACTED"
                    redactedKwargs["data"] = redactedKwargsData
                if "headers" in redactedKwargs:
                    redactedKwargsHeaders = redactedKwargs["headers"]
                    if (
                        "Tapo_tag" in redactedKwargsHeaders
                        and redactedKwargsHeaders["Tapo_tag"] != ""
                    ):
                        redactedKwargsHeaders["Tapo_tag"] = "REDACTED"
                    if (
                        "Host" in redactedKwargsHeaders
                        and redactedKwargsHeaders["Host"] != ""
                    ):
                        redactedKwargsHeaders["Host"] = "REDACTED"
                    if (
                        "Referer" in redactedKwargsHeaders
                        and redactedKwargsHeaders["Referer"] != ""
                    ):
                        redactedKwargsHeaders["Referer"] = "REDACTED"
                    redactedKwargs["headers"] = redactedKwargsHeaders
            self.debugLog("New request:")
            self.debugLog(redactedKwargs)
        response = session.request(method, url, **kwargs)
        if self.printDebugInformation:
            self.debugLog(response.status_code)
            try:
                loadJson = json.loads(response.text)
                if self.redactConfidentialInformation:
                    if "result" in loadJson:
                        if (
                            "stok" in loadJson["result"]
                            and loadJson["result"]["stok"] != ""
                        ):
                            loadJson["result"]["stok"] = "REDACTED"
                        if "data" in loadJson["result"]:
                            if (
                                "key" in loadJson["result"]["data"]
                                and loadJson["result"]["data"]["key"] != ""
                            ):
                                loadJson["result"]["data"]["key"] = "REDACTED"
                            if (
                                "nonce" in loadJson["result"]["data"]
                                and loadJson["result"]["data"]["nonce"] != ""
                            ):
                                loadJson["result"]["data"]["nonce"] = "REDACTED"
                            if (
                                "device_confirm" in loadJson["result"]["data"]
                                and loadJson["result"]["data"]["device_confirm"] != ""
                            ):
                                loadJson["result"]["data"][
                                    "device_confirm"
                                ] = "REDACTED"
                self.debugLog(loadJson)
            except Exception as err:
                self.debugLog("Failed to load json:" + str(err))

        if self.reuseSession is False:
            response.close()
            session.close()
        return response

    def isSecureConnection(self):
        if self.isSecureConnectionCached is None:
            url = "https://{host}".format(host=self.getControlHost())
            data = {
                "method": "login",
                "params": {
                    "encrypt_type": "3",
                    "username": self.user,
                },
            }
            res = self.request(
                "POST", url, data=json.dumps(data), headers=self.headers, verify=False
            )
            response = res.json()
            self.isSecureConnectionCached = (
                "error_code" in response
                and response["error_code"] == -40413
                and "result" in response
                and "data" in response["result"]
                and "encrypt_type" in response["result"]["data"]
                and "3" in response["result"]["data"]["encrypt_type"]
            )
        return self.isSecureConnectionCached

    def validateDeviceConfirm(self, nonce, deviceConfirm):
        self.passwordEncryptionMethod = None
        hashedNoncesWithSHA256 = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self.hashedSha256Password.encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        hashedNoncesWithMD5 = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self.hashedPassword.encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        if deviceConfirm == (hashedNoncesWithSHA256 + nonce + self.cnonce):
            self.passwordEncryptionMethod = EncryptionMethod.SHA256
        elif deviceConfirm == (hashedNoncesWithMD5 + nonce + self.cnonce):
            self.passwordEncryptionMethod = EncryptionMethod.MD5
        return self.passwordEncryptionMethod is not None

    def getTag(self, request):
        tag = (
            hashlib.sha256(
                self.getHashedPassword().encode("utf8") + self.cnonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        tag = (
            hashlib.sha256(
                tag.encode("utf8")
                + json.dumps(request).encode("utf8")
                + str(self.seq).encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        return tag

    def generateEncryptionToken(self, tokenType, nonce):
        hashedKey = (
            hashlib.sha256(
                self.cnonce.encode("utf8")
                + self.getHashedPassword().encode("utf8")
                + nonce.encode("utf8")
            )
            .hexdigest()
            .upper()
        )
        return hashlib.sha256(
            (
                tokenType.encode("utf8")
                + self.cnonce.encode("utf8")
                + nonce.encode("utf8")
                + hashedKey.encode("utf8")
            )
        ).digest()[:16]

    def getEncryptionMethod(self):
        return self.passwordEncryptionMethod

    def getHashedPassword(self):
        if self.passwordEncryptionMethod == EncryptionMethod.MD5:
            return self.hashedPassword
        elif self.passwordEncryptionMethod == EncryptionMethod.SHA256:
            return self.hashedSha256Password
        else:
            raise Exception("Failure detecting hashing algorithm.")

    def refreshStok(self, loginRetryCount=0):
        self.debugLog("Refreshing stok...")
        self.cnonce = generate_nonce(8).decode().upper()
        url = "https://{host}".format(host=self.getControlHost())
        if self.isSecureConnection():
            self.debugLog("Connection is secure.")
            data = {
                "method": "login",
                "params": {
                    "cnonce": self.cnonce,
                    "encrypt_type": "3",
                    "username": self.user,
                },
            }
        else:
            self.debugLog("Connection is insecure.")
            data = {
                "method": "login",
                "params": {
                    "hashed": True,
                    "password": self.hashedPassword,
                    "username": self.user,
                },
            }
        res = self.request(
            "POST", url, data=json.dumps(data), headers=self.headers, verify=False
        )
        self.debugLog("Status code: " + str(res.status_code))

        if res.status_code == 401:
            try:
                data = res.json()
                if data["result"]["data"]["code"] == -40411:
                    self.debugLog("Code is -40411, raising Exception.")
                    raise Exception("Invalid authentication data")
            except Exception as e:
                if str(e) == "Invalid authentication data":
                    raise e
                else:
                    pass

        responseData = res.json()
        if self.isSecureConnection():
            self.debugLog("Processing secure response.")
            if (
                "result" in responseData
                and "data" in responseData["result"]
                and "nonce" in responseData["result"]["data"]
                and "device_confirm" in responseData["result"]["data"]
            ):
                self.debugLog("Validating device confirm.")
                nonce = responseData["result"]["data"]["nonce"]
                if self.validateDeviceConfirm(
                    nonce, responseData["result"]["data"]["device_confirm"]
                ):  # sets self.passwordEncryptionMethod, password verified on client, now request stok
                    self.debugLog("Signing in with digestPasswd.")
                    digestPasswd = (
                        hashlib.sha256(
                            self.getHashedPassword().encode("utf8")
                            + self.cnonce.encode("utf8")
                            + nonce.encode("utf8")
                        )
                        .hexdigest()
                        .upper()
                    )
                    data = {
                        "method": "login",
                        "params": {
                            "cnonce": self.cnonce,
                            "encrypt_type": "3",
                            "digest_passwd": (
                                digestPasswd.encode("utf8")
                                + self.cnonce.encode("utf8")
                                + nonce.encode("utf8")
                            ).decode(),
                            "username": self.user,
                        },
                    }
                    res = self.request(
                        "POST",
                        url,
                        data=json.dumps(data),
                        headers=self.headers,
                        verify=False,
                    )
                    responseData = res.json()
                    if (
                        "result" in responseData
                        and "start_seq" in responseData["result"]
                    ):
                        if (
                            "user_group" in responseData["result"]
                            and responseData["result"]["user_group"] != "root"
                        ):
                            self.debugLog(
                                "Incorrect user_group detected, raising Exception."
                            )
                            # encrypted control via 3rd party account does not seem to be supported
                            # see https://github.com/JurajNyiri/HomeAssistant-Tapo-Control/issues/456
                            raise Exception("Invalid authentication data")
                        self.debugLog("Geneerating encryption tokens.")
                        self.lsk = self.generateEncryptionToken("lsk", nonce)
                        self.ivb = self.generateEncryptionToken("ivb", nonce)
                        self.seq = responseData["result"]["start_seq"]
                else:
                    if (
                        self.retryStok
                        and (
                            "error_code" in responseData
                            and responseData["error_code"] == -40413
                        )
                        and loginRetryCount < MAX_LOGIN_RETRIES
                    ):
                        loginRetryCount += 1
                        self.debugLog(
                            f"Incorrect device_confirm value, retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
                        )
                        return self.refreshStok(loginRetryCount)
                    else:
                        self.debugLog(
                            "Incorrect device_confirm value, raising Exception."
                        )
                        raise Exception("Invalid authentication data")
        else:
            self.passwordEncryptionMethod = EncryptionMethod.MD5
        if (
            "result" in responseData
            and "data" in responseData["result"]
            and "time" in responseData["result"]["data"]
            and "max_time" in responseData["result"]["data"]
            and "sec_left" in responseData["result"]["data"]
            and responseData["result"]["data"]["sec_left"] > 0
        ):
            raise Exception(
                f"Temporary Suspension: Try again in {str(responseData['result']['data']['sec_left'])} seconds"
            )
        if (
            "data" in responseData
            and "code" in responseData["data"]
            and "sec_left" in responseData["data"]
            and responseData["data"]["code"] == -40404
            and responseData["data"]["sec_left"] > 0
        ):
            raise Exception(
                f"Temporary Suspension: Try again in {str(responseData['data']['sec_left'])} seconds"
            )

        if self.responseIsOK(res):
            self.debugLog("Saving stok.")
            self.stok = res.json()["result"]["stok"]
            return self.stok
        if (
            self.retryStok
            and ("error_code" in responseData and responseData["error_code"] == -40413)
            and loginRetryCount < MAX_LOGIN_RETRIES
        ):
            loginRetryCount += 1
            self.debugLog(
                f"Unexpected response, retrying: {loginRetryCount}/{MAX_LOGIN_RETRIES}."
            )
            return self.refreshStok(loginRetryCount)
        else:
            self.debugLog("Unexpected response, raising Exception.")
            raise Exception("Invalid authentication data")

    def responseIsOK(self, res, data=None):
        if (res.status_code != 200 and not self.isSecureConnection()) or (
            res.status_code != 200
            and res.status_code != 500
            and self.isSecureConnection()  # pass responseIsOK for secure connections 500 which are communicating expiring session
        ):
            raise Exception(
                "Error communicating with Tapo Camera. Status code: "
                + str(res.status_code)
            )
        try:
            if data is None:
                data = res.json()
            if "error_code" not in data or data["error_code"] == 0:
                return True
            return False
        except Exception as e:
            raise Exception("Unexpected response from Tapo Camera: " + str(e))

    def executeFunction(self, method, params, retry=False):
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

        if type(data) == list:
            return data

        if "result" in data and (
            "error_code" not in data
            or ("error_code" in data and data["error_code"] == 0)
        ):
            return data["result"]
        else:
            if "error_code" in data and data["error_code"] == -64303 and retry is False:
                self.setCruise(False)
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

    def encryptRequest(self, request):
        cipher = AES.new(self.lsk, AES.MODE_CBC, self.ivb)
        ct_bytes = cipher.encrypt(pad(request, AES.block_size))
        return ct_bytes

    def decryptResponse(self, response):
        cipher = AES.new(self.lsk, AES.MODE_CBC, self.ivb)
        pt = cipher.decrypt(response)
        return unpad(pt, AES.block_size)

    def performRequest(self, requestData, loginRetryCount=0):
        self.ensureAuthenticated()
        authValid = True
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

        if self.seq is not None and self.isSecureConnection():
            fullRequest = {
                "method": "securePassthrough",
                "params": {
                    "request": base64.b64encode(
                        self.encryptRequest(json.dumps(fullRequest).encode("utf-8"))
                    ).decode("utf8")
                },
            }
            self.headers["Seq"] = str(self.seq)
            try:
                self.headers["Tapo_tag"] = self.getTag(fullRequest)
            except Exception as err:
                if str(err) == "Failure detecting hashing algorithm.":
                    authValid = False
                    self.debugLog(
                        "Failure detecting hashing algorithm on getTag, reauthenticating."
                    )
                else:
                    raise err
            self.seq += 1

        res = self.request(
            "POST",
            url,
            data=json.dumps(fullRequest),
            headers=self.headers,
            verify=False,
        )
        responseData = res.json()
        if (
            self.isSecureConnection()
            and "result" in responseData
            and "response" in responseData["result"]
        ):
            encryptedResponse = responseData["result"]["response"]
            encryptedResponse = base64.b64decode(responseData["result"]["response"])
            try:
                responseJSON = json.loads(self.decryptResponse(encryptedResponse))
            except Exception as err:
                if (
                    str(err) == "Padding is incorrect."
                    or str(err) == "PKCS#7 padding is incorrect."
                ):
                    self.debugLog(f"{str(err)} Reauthenticating.")
                    authValid = False
                else:
                    raise err
        else:
            responseJSON = res.json()
        if not authValid or not self.responseIsOK(res, responseJSON):
            #  -40401: Invalid Stok
            if (
                not authValid
                or (
                    responseJSON
                    and "error_code" in responseJSON
                    and (
                        responseJSON["error_code"] == -40401
                        or responseJSON["error_code"] == -1
                    )
                )
            ) and loginRetryCount < MAX_LOGIN_RETRIES:
                self.refreshStok()
                return self.performRequest(requestData, loginRetryCount + 1)
            else:
                raise Exception(
                    "Error: {}, Response: {}".format(
                        self.getErrorMessage(responseJSON["error_code"]),
                        json.dumps(responseJSON),
                    )
                )

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

    def getMediaSession(self):
        return HttpMediaSession(
            self.host,
            self.cloudPassword,
            self.superSecretKey,
            self.getEncryptionMethod(),
        )  # pragma: no cover

    def getChildDevices(self):
        childDevices = self.performRequest(
            {
                "method": "getChildDeviceList",
                "params": {"childControl": {"start_index": 0}},
            }
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
            if timeReturned:
                nowTS = int(datetime.timestamp(datetime.now()))
                self.timeCorrection = (
                    nowTS - currentTime["system"]["clock_status"]["seconds_from_1970"]
                )
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
            "method": "set",
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
        return self.performRequest(
            {"method": "get", "function": {"name": ["module_spec"]}}
        )

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

    def getFirmwareAutoUpgradeConfig(self):
        return self.executeFunction(
            "getFirmwareAutoUpgradeConfig",
            {"auto_upgrade": {"name": ["common"]}},
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
                "method": "get",
                "audio_capability": {"name": ["device_speaker", "device_microphone"]},
            }
        )

    def getAudioConfig(self):
        return self.executeFunction(
            "getAudioConfig",
            {"method": "get", "audio_config": {"name": ["speaker", "microphone"]}},
        )

    def setSpeakerVolume(self, volume):
        return self.executeFunction(
            "setSpeakerVolume",
            {"method": "set", "audio_config": {"speaker": {"volume": volume}}},
        )

    def setMicrophone(self, volume=None, mute=None, noise_cancelling=None):
        params = {"method": "set", "audio_config": {"microphone": {}}}
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
        return self.performRequest({"method": "get", "cet": {"name": ["vhttpd"]}})

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

    def getBasicInfo(self):
        return self.executeFunction(
            "getDeviceInfo", {"device_info": {"name": ["basic_info"]}}
        )

    def getTime(self):
        return self.executeFunction(
            "getClockStatus", {"system": {"name": "clock_status"}}
        )

    def getDSTRule(self):
        return self.executeFunction("getDstRule", {"system": {"name": "dst"}})

    # does not work for child devices, function discovery needed
    def getMotorCapability(self):
        return self.performRequest({"method": "get", "motor": {"name": ["capability"]}})

    def setPrivacyMode(self, enabled):
        return self.executeFunction(
            "setLensMaskConfig",
            {"lens_mask": {"lens_mask_info": {"enabled": "on" if enabled else "off"}}},
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
                "method": "set",
                "msg_alarm": {
                    "chn1_msg_alarm_info": {
                        "alarm_type": "0",
                        "enabled": "on" if enabled else "off",
                        "light_type": "0",
                        "alarm_mode": alarm_mode,
                    }
                },
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
            {"method": "do", "motor": {"move": {"x_coord": str(x), "y_coord": str(y)}}}
        )

    # todo child
    def moveMotorStep(self, angle):
        if not (0 <= angle < 360):
            raise Exception("Angle must be in a range 0 <= angle < 360")

        return self.performRequest(
            {"method": "do", "motor": {"movestep": {"direction": str(angle)}}}
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
        return self.performRequest({"method": "do", "motor": {"manual_cali": ""}})

    def format(self):
        return self.executeFunction(
            "formatSdCard", {"harddisk_manage": {"format_hd": "1"}}
        )  # pragma: no cover

    def setLEDEnabled(self, enabled):
        return self.executeFunction(
            "setLedStatus", {"led": {"config": {"enabled": "on" if enabled else "off"}}}
        )

    def getUserID(self, forceReload=False):
        if not self.userID or forceReload is True:
            response = self.userID = self.performRequest(
                {
                    "method": "multipleRequest",
                    "params": {
                        "requests": [
                            {
                                "method": "getUserID",
                                "params": {"system": {"get_user_id": "null"}},
                            }
                        ]
                    },
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

    def getRecordings(self, date, start_index=0, end_index=999999999):
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
        return self.performRequest({"method": "get", "image": {"name": "common"}})

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

    def setPetDetection(self, enabled, sensitivity=False):
        data = {"pet_detection": {"detection": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            data["pet_detection"]["detection"]["sensitivity"] = (
                self.__getSensitivityNumber(sensitivity)
            )

        return self.executeFunction("setPetDetectionConfig", data)

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

    def setCruise(self, enabled, coord=False):
        if coord not in ["x", "y"] and coord is not False:
            raise Exception("Invalid coord parameter. Can be 'x' or 'y'.")
        if enabled and coord is not False:
            return self.executeFunction(
                "cruiseMove",
                {"motor": {"cruise": {"coord": coord}}},
            )
        else:
            return self.executeFunction(
                "cruiseStop",
                {"motor": {"cruise_stop": {}}},
            )

    def reboot(self):
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
            "deletePreset", {"preset": {"remove_preset": {"id": [presetID]}}}
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
                "method": "do",
                "msg_alarm": {"manual_msg_alarm": {"action": "start"}},
            }
        )

    # does not work for child devices, function discovery needed
    def stopManualAlarm(self):
        return self.performRequest(
            {
                "method": "do",
                "msg_alarm": {"manual_msg_alarm": {"action": "stop"}},
            }
        )

    def getBatteryStatus(self):
        return self.executeFunction("getBatteryStatus", {"battery": {"name": "status"}})

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
                "method": "multipleRequest",
                "params": {
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
                },
            }
        )

    def startFirmwareUpgrade(self):
        try:
            self.performRequest(
                {"method": "do", "cloud_config": {"fw_download": "null"}}
            )
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
        requestData = {
            "method": "multipleRequest",
            "params": {
                "requests": [
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
                        "params": {"image_capability": {"name": ["supplement_lamp"]}},
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
                            "audio_config": {"name": ["speaker", "microphone"]},
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
                ]
            },
        }
        if len(omit_methods) != 0:
            filtered_requests = [
                request
                for request in requestData["params"]["requests"]
                if request.get("method") not in omit_methods
            ]
            requestData["params"]["requests"] = filtered_requests

        results = self.performRequest(requestData)

        # handle malformed / unexpected response from camera
        if len(requestData["params"]["requests"]) != len(
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
        for request in requestData["params"]["requests"]:
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

        if len(returnData["getPresetConfig"]) == 1:
            if returnData["getPresetConfig"][0]:
                self.presets = self.processPresetsResponse(
                    returnData["getPresetConfig"][0]
                )
        else:
            raise Exception("Unexpected number of getPresetConfig responses")
        return returnData
