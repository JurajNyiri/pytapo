#
# Author: See contributors at https://github.com/JurajNyiri/pytapo/graphs/contributors
#

import hashlib
import json

import requests
import urllib3

from .const import ERROR_CODES

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Tapo:
    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        self.stok = False
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
            return data["error_code"] == 0
        except Exception as e:
            raise Exception("Unexpected response from Tapo Camera: " + str(e))

    def performRequest(self, requestData, loginRetry=False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        res = requests.post(
            url, data=json.dumps(requestData), headers=self.headers, verify=False
        )
        if self.responseIsOK(res):
            return res.json()
        else:
            data = json.loads(res.text)
            #  -40401: Invalid Stok
            if (
                data
                and "error_code" in data
                and data["error_code"] == -40401
                and not loginRetry
            ):
                self.refreshStok()
                return self.performRequest(requestData, True)
            else:
                raise Exception(
                    "Error: "
                    + self.getErrorMessage(data["error_code"])
                    + " Response:"
                    + json.dumps(data)
                )

    def getOsd(self):
        return self.performRequest(
            {
                "method": "get",
                "OSD": {"name": ["date", "week", "font"], "table": ["label_info"]},
            }
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
            labelEnabled = False
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

    def getModuleSpec(self):
        return self.performRequest(
            {"method": "get", "function": {"name": ["module_spec"]}}
        )

    def getPrivacyMode(self):
        data = {"method": "get", "lens_mask": {"name": ["lens_mask_info"]}}
        return self.performRequest(data)["lens_mask"]["lens_mask_info"]

    def getMotionDetection(self):
        data = {"method": "get", "motion_detection": {"name": ["motion_det"]}}
        return self.performRequest(data)["motion_detection"]["motion_det"]

    def getAlarm(self):
        data = {"method": "get", "msg_alarm": {"name": ["chn1_msg_alarm_info"]}}
        return self.performRequest(data)["msg_alarm"]["chn1_msg_alarm_info"]

    def getLED(self):
        data = {"method": "get", "led": {"name": ["config"]}}
        return self.performRequest(data)["led"]["config"]

    def getAutoTrackTarget(self):
        data = {"method": "get", "target_track": {"name": ["target_track_info"]}}
        return self.performRequest(data)["target_track"]["target_track_info"]

    def getAudioSpec(self):
        return self.performRequest(
            {
                "method": "get",
                "audio_capability": {"name": ["device_speaker", "device_microphone"]},
            }
        )

    def getVhttpd(self):
        return self.performRequest({"method": "get", "cet": {"name": ["vhttpd"]}})

    def getBasicInfo(self):
        return self.performRequest(
            {"method": "get", "device_info": {"name": ["basic_info"]}}
        )

    def getTime(self):
        return self.performRequest(
            {"method": "get", "system": {"name": ["clock_status"]}}
        )

    def getMotorCapability(self):
        return self.performRequest({"method": "get", "motor": {"name": ["capability"]}})

    def setPrivacyMode(self, enabled):
        return self.performRequest(
            {
                "method": "set",
                "lens_mask": {
                    "lens_mask_info": {"enabled": "on" if enabled else "off"}
                },
            }
        )

    def setAlarm(self, enabled, soundEnabled=True, lightEnabled=True):
        alarm_mode = []

        if not soundEnabled and not lightEnabled:
            raise Exception("You need to use at least sound or light for alarm")

        if soundEnabled:
            alarm_mode.append("sound")
        if lightEnabled:
            alarm_mode.append("light")

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

    def moveMotor(self, x, y):
        return self.performRequest(
            {
                "method": "do",
                "motor": {"move": {"x_coord": str(x), "y_coord": str(y)}},
            }
        )

    def moveMotorStep(self, angle):
        if not (0 <= angle < 360):
            raise Exception("Angle must be in a range 0 <= angle < 360")

        return self.performRequest(
            {
                "method": "do",
                "motor": {"movestep": {"direction": str(angle)}},
            }
        )

    def format(self):
        return self.performRequest(
            {"method": "do", "harddisk_manage": {"format_hd": "1"}}
        )  # pragma: no cover

    def setLEDEnabled(self, enabled):
        return self.performRequest(
            {
                "method": "set",
                "led": {"config": {"enabled": "on" if enabled else "off"}},
            }
        )

    def setDayNightMode(self, inf_type):
        if inf_type not in ["off", "on", "auto"]:
            raise Exception("Invalid inf_type, can be off, on or auto")
        return self.performRequest(
            {
                "method": "set",
                "image": {"common": {"inf_type": inf_type}},
            }
        )

    def getCommonImage(self):
        return self.performRequest(
            {
                "method": "get",
                "image": {"name": "common"},
            }
        )

    def setMotionDetection(self, enabled, sensitivity=False):
        data = {
            "method": "set",
            "motion_detection": {"motion_det": {"enabled": "on" if enabled else "off"}},
        }
        if sensitivity:
            if sensitivity == "high":
                data["motion_detection"]["motion_det"]["digital_sensitivity"] = "80"
            elif sensitivity == "normal":
                data["motion_detection"]["motion_det"]["digital_sensitivity"] = "50"
            elif sensitivity == "low":
                data["motion_detection"]["motion_det"]["digital_sensitivity"] = "20"
            else:
                raise Exception("Invalid sensitivity, can be low, normal or high")

        return self.performRequest(data)

    def setAutoTrackTarget(self, enabled):
        return self.performRequest(
            {
                "method": "set",
                "target_track": {
                    "target_track_info": {"enabled": "on" if enabled else "off"}
                },
            }
        )

    def reboot(self):
        return self.performRequest({"method": "do", "system": {"reboot": "null"}})

    def getPresets(self):
        data = self.performRequest({"method": "get", "preset": {"name": ["preset"]}})
        self.presets = {
            id: data["preset"]["preset"]["name"][key]
            for key, id in enumerate(data["preset"]["preset"]["id"])
        }
        return self.presets

    def savePreset(self, name):
        self.performRequest(
            {
                "method": "do",
                "preset": {"set_preset": {"name": str(name), "save_ptz": "1"}},
            }
        )
        self.getPresets()
        return True

    def deletePreset(self, presetID):
        if not str(presetID) in self.presets:
            raise Exception("Preset " + str(presetID) + " is not set in the app")

        self.performRequest(
            {"method": "do", "preset": {"remove_preset": {"id": [presetID]}}}
        )
        self.getPresets()
        return True

    def setPreset(self, presetID):
        if not str(presetID) in self.presets:
            raise Exception("Preset " + str(presetID) + " is not set in the app")
        return self.performRequest(
            {"method": "do", "preset": {"goto_preset": {"id": str(presetID)}}}
        )

    @staticmethod
    def getErrorMessage(errorCode):
        if str(errorCode) in ERROR_CODES:
            return str(ERROR_CODES[str(errorCode)])
        else:
            return str(errorCode)
