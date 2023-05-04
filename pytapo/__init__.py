#
# Author: See contributors at https://github.com/JurajNyiri/pytapo/graphs/contributors
#


import hashlib
import json

import requests
import urllib3
from warnings import warn

from .const import ERROR_CODES, MAX_LOGIN_RETRIES
from .media_stream.session import HttpMediaSession
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Tapo:
    def __init__(
        self, host, user, password, cloudPassword="", superSecretKey="", childID=None
    ):
        self.host = host
        self.user = user
        self.password = password
        self.cloudPassword = cloudPassword
        self.superSecretKey = superSecretKey
        self.stok = False
        self.userID = False
        self.childID = childID
        self.timeCorrection = False
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
        return "https://{host}/stok={stok}/ds".format(host=self.host, stok=self.stok)

    def getStreamURL(self):
        return "{host}:8800".format(host=self.host)

    def ensureAuthenticated(self):
        if not self.stok:
            return self.refreshStok()
        return True

    def refreshStok(self):
        url = "https://{host}".format(host=self.host)
        data = {
            "method": "login",
            "params": {
                "hashed": True,
                "password": self.hashedPassword,
                "username": self.user,
            },
        }
        res = requests.post(
            url, data=json.dumps(data), headers=self.headers, verify=False
        )
        if res.status_code == 401:
            try:
                data = res.json()
                if data["result"]["data"]["code"] == -40411:
                    raise Exception("Invalid authentication data")
            except Exception as e:
                if str(e) == "Invalid authentication data":
                    raise e
                else:
                    pass

        if self.responseIsOK(res):
            self.stok = res.json()["result"]["stok"]
            return self.stok
        raise Exception("Invalid authentication data")

    def responseIsOK(self, res):
        if res.status_code != 200:
            raise Exception(
                "Error communicating with Tapo Camera. Status code: "
                + str(res.status_code)
            )
        try:
            data = res.json()
            if "error_code" not in data or data["error_code"] == 0:
                return True
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
                    data["err_msg"]
                    if "err_msg" in data
                    else self.getErrorMessage(data["error_code"]),
                    json.dumps(data),
                )
            )

    def performRequest(self, requestData, loginRetryCount=0):
        self.ensureAuthenticated()
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
        res = requests.post(
            url, data=json.dumps(fullRequest), headers=self.headers, verify=False
        )
        if not self.responseIsOK(res):
            data = json.loads(res.text)
            #  -40401: Invalid Stok
            if (
                data
                and "error_code" in data
                and data["error_code"] == -40401
                and loginRetryCount < MAX_LOGIN_RETRIES
            ):
                self.refreshStok()
                return self.performRequest(requestData, loginRetryCount + 1)
            else:
                raise Exception(
                    "Error: {}, Response: {}".format(
                        self.getErrorMessage(data["error_code"]), json.dumps(data)
                    )
                )

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

    def getMediaSession(self):
        return HttpMediaSession(
            self.host, self.cloudPassword, self.superSecretKey
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
        if not timeCorrection:
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
                        "end_index": 99,
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

    # does not work for child devices, function discovery needed
    def getVhttpd(self):
        return self.performRequest({"method": "get", "cet": {"name": ["vhttpd"]}})

    def getBasicInfo(self):
        return self.executeFunction(
            "getDeviceInfo", {"device_info": {"name": ["basic_info"]}}
        )

    def getTime(self):
        return self.executeFunction(
            "getClockStatus", {"system": {"name": "clock_status"}}
        )

    # does not work for child devices, function discovery needed
    def getMotorCapability(self):
        return self.performRequest({"method": "get", "motor": {"name": ["capability"]}})

    def setPrivacyMode(self, enabled):
        return self.executeFunction(
            "setLensMaskConfig",
            {"lens_mask": {"lens_mask_info": {"enabled": "on" if enabled else "off"}}},
        )

    def setMediaEncrypt(self, enabled):
        return self.executeFunction(
            "setMediaEncrypt",
            {"cet": {"media_encrypt": {"enabled": "on" if enabled else "off"}}},
        )

    # todo child
    def setAlarm(self, enabled, soundEnabled=True, lightEnabled=True):
        alarm_mode = []

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

    def getUserID(self):
        if not self.userID:
            self.userID = self.performRequest(
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
            )["result"]["responses"][0]["result"]["user_id"]
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

    # does not work for child devices, function discovery needed
    def getCommonImage(self):
        warn("Prefer to use a specific value getter", DeprecationWarning, stacklevel=2)
        return self.performRequest({"method": "get", "image": {"name": "common"}})

    def __getSensitivityNumber(self, sensitivity):
        if sensitivity.isnumeric():
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

    def setMotionDetection(self, enabled, sensitivity=False):
        data = {
            "motion_detection": {"motion_det": {"enabled": "on" if enabled else "off"}},
        }
        if sensitivity:
            data["motion_detection"]["motion_det"][
                "digital_sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)
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
            data["people_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)
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
            data["vehicle_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)
        return self.executeFunction("setVehicleDetectionConfig", data)

    def getPetDetection(self):
        return self.executeFunction(
            "getPetDetectionConfig",
            {"pet_detection": {"name": ["detection"]}},
        )["pet_detection"]["detection"]

    def setPetDetection(self, enabled, sensitivity=False):
        data = {"pet_detection": {"detection": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            data["pet_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)

        return self.executeFunction("setPetDetectionConfig", data)

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
            data["bark_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)

        return self.executeFunction("setBarkDetectionConfig", data)

    def setMeowDetection(self, enabled, sensitivity=False):
        data = {
            "meow_detection": {"detection": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            data["meow_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)

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
            data["glass_detection"]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)

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

    def getPresets(self):
        data = self.executeFunction("getPresetConfig", {"preset": {"name": ["preset"]}})
        self.presets = {
            id: data["preset"]["preset"]["name"][key]
            for key, id in enumerate(data["preset"]["preset"]["id"])
        }
        return self.presets

    def savePreset(self, name):
        self.executeFunction(
            "addMotorPostion",  # yes, there is a typo in function name
            {"preset": {"set_preset": {"name": str(name), "save_ptz": "1"}}},
        )
        self.getPresets()
        return True

    def deletePreset(self, presetID):
        if not str(presetID) in self.presets:
            raise Exception("Preset {} is not set in the app".format(str(presetID)))

        self.executeFunction(
            "deletePreset", {"preset": {"remove_preset": {"id": [presetID]}}}
        )
        self.getPresets()
        return True

    def setPreset(self, presetID):
        if not str(presetID) in self.presets:
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

    # Used for purposes of HomeAssistant-Tapo-Control
    # Uses method names from https://md.depau.eu/s/r1Ys_oWoP
    def getMost(self):
        requestData = {
            "method": "multipleRequest",
            "params": {
                "requests": [
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
                    {"method": "getLightTypeList", "params": {"msg_alarm": {}}},
                    {"method": "getSirenStatus", "params": {"msg_alarm": {}}},
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
                ]
            },
        }
        results = self.performRequest(requestData)

        returnData = {}
        # todo finish on child
        i = 0
        for result in results["result"]["responses"]:
            if (
                "error_code" in result and result["error_code"] == 0
            ) and "result" in result:
                returnData[result["method"]] = result["result"]
            else:
                if "method" in result:
                    returnData[result["method"]] = False
                else:  # some cameras are not returning method for error messages
                    returnData[requestData["params"]["requests"][i]["method"]] = False
            i += 1
        return returnData
