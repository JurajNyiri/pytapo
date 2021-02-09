import os
import pytest
import json
import time
from pytapo import Tapo
import mock

user = os.environ.get("PYTAPO_USER")
password = os.environ.get("PYTAPO_PASSWORD")
invalidPassword = "{password}_invalid".format(password=password)
host = os.environ.get("PYTAPO_IP")

"""
util functions for unit tests
"""


def setOsd(tapo, values):
    data = {
        "origLabelEnabled": values["OSD"]["label_info"][0]["label_info_1"]["enabled"],
        "origLabelX": values["OSD"]["label_info"][0]["label_info_1"]["x_coor"],
        "origLabelY": values["OSD"]["label_info"][0]["label_info_1"]["y_coor"],
        "origDateEnabled": values["OSD"]["date"]["enabled"],
        "origDateX": values["OSD"]["date"]["x_coor"],
        "origDateY": values["OSD"]["date"]["y_coor"],
        "origWeekEnabled": values["OSD"]["week"]["enabled"],
        "origWeekX": values["OSD"]["week"]["x_coor"],
        "origWeekY": values["OSD"]["week"]["y_coor"],
    }

    if "text" in values["OSD"]["label_info"][0]["label_info_1"]:
        data["origLabelText"] = values["OSD"]["label_info"][0]["label_info_1"]["text"]
    else:
        data["origLabelText"] = ""

    tapo.setOsd(
        data["origLabelText"],
        data["origDateEnabled"] == "on",
        data["origLabelEnabled"] == "on",
        data["origWeekEnabled"] == "on",
        int(data["origDateX"]),
        int(data["origDateY"]),
        int(data["origLabelX"]),
        int(data["origLabelY"]),
        int(data["origWeekX"]),
        int(data["origWeekY"]),
    )
    return data


def getPresetsMock(classObj):
    raise Exception("Mock exception")


"""
unit tests below
"""


def test_refreshStok_success():
    tapo = Tapo(host, user, password)
    result = tapo.refreshStok()
    assert isinstance(result, str)


def test_refreshStok_failure():
    with pytest.raises(Exception) as err:
        tapo = Tapo(host, user, invalidPassword)
        tapo.refreshStok()
    assert "Invalid authentication data" in str(err.value)


def test_getHostURL():
    tapo = Tapo(host, user, password)
    hostURL = tapo.getHostURL()
    assert "https://{host}/stok=".format(host=host) in hostURL
    assert "/ds" in hostURL


def test_ensureAuthenticated():
    tapo = Tapo(host, user, password)
    result = tapo.ensureAuthenticated()
    assert result is True


def test_responseIsOK_success():
    tapo = Tapo(host, user, password)

    class AttributeDict(dict):
        status_code = 200
        text = '{"error_code":0}'

        def json(self):
            return json.loads(self.text)

    result = tapo.responseIsOK(AttributeDict())
    assert result is True


def test_responseIsOK_failure():
    tapo = Tapo(host, user, password)

    class AttributeDict(dict):
        status_code = 200
        text = '{"error_code":404}'

        def json(self):
            return json.loads(self.text)

    result = tapo.responseIsOK(AttributeDict())
    assert result is False

    class AttributeDict(dict):
        status_code = 200
        text = "not json"

        def json(self):
            return json.loads(self.text)

    with pytest.raises(Exception) as err:
        result = tapo.responseIsOK(AttributeDict())

    assert "Unexpected response from Tapo Camera: " in str(err.value)

    class AttributeDict(dict):
        status_code = 404
        text = "not json"

        def json(self):
            return json.loads(self.text)

    with pytest.raises(Exception) as err:
        tapo.responseIsOK(AttributeDict())

    assert "Error communicating with Tapo Camera. Status code: 404" == str(err.value)


def test_performRequest_failure():
    tapo = Tapo(host, user, password)
    with pytest.raises(Exception) as err:
        tapo.performRequest({"invalidData": "test123"})
    assert (
        'Error: -40210 Response:{"result": {"responses": []}, "error_code": -40210}'
        == str(err.value)
    )


def test_performRequest_invalidStok():
    tapo = Tapo(host, user, password)
    tapo.stok = "invalidStok"
    result = tapo.getOsd()
    assert "OSD" in result
    assert result["error_code"] == 0


def test_getOsd():
    tapo = Tapo(host, user, password)
    result = tapo.getOsd()
    assert "OSD" in result
    assert result["error_code"] == 0


def test_setOsd_success():
    tapo = Tapo(host, user, password)
    originalOsd = tapo.getOsd()

    tapo.setOsd(
        "unit test",
        False,
        False,
        False,
        1,
        2,
        3,
        4,
        5,
        6,
    )
    result1 = tapo.getOsd()

    tapo.setOsd(
        "unit test 2",
        True,
        True,
        True,
        7,
        8,
        9,
        10,
        11,
        12,
    )
    result2 = tapo.getOsd()

    tapo.setOsd(
        "",
    )
    result3 = tapo.getOsd()
    origData = setOsd(tapo, originalOsd)

    assert result1["OSD"]["label_info"][0]["label_info_1"]["text"] == "unit test"
    assert result1["OSD"]["label_info"][0]["label_info_1"]["enabled"] == "off"
    assert result1["OSD"]["label_info"][0]["label_info_1"]["x_coor"] == "3"
    assert result1["OSD"]["label_info"][0]["label_info_1"]["y_coor"] == "4"
    assert result1["OSD"]["date"]["enabled"] == "off"
    assert result1["OSD"]["date"]["x_coor"] == "1"
    assert result1["OSD"]["date"]["y_coor"] == "2"
    assert result1["OSD"]["week"]["enabled"] == "off"
    assert result1["OSD"]["week"]["x_coor"] == "5"
    assert result1["OSD"]["week"]["y_coor"] == "6"

    assert result2["OSD"]["label_info"][0]["label_info_1"]["text"] == "unit test 2"
    assert result2["OSD"]["label_info"][0]["label_info_1"]["enabled"] == "on"
    assert result2["OSD"]["label_info"][0]["label_info_1"]["x_coor"] == "9"
    assert result2["OSD"]["label_info"][0]["label_info_1"]["y_coor"] == "10"
    assert result2["OSD"]["date"]["enabled"] == "on"
    assert result2["OSD"]["date"]["x_coor"] == "7"
    assert result2["OSD"]["date"]["y_coor"] == "8"
    assert result2["OSD"]["week"]["enabled"] == "on"
    assert result2["OSD"]["week"]["x_coor"] == "11"
    assert result2["OSD"]["week"]["y_coor"] == "12"

    assert result3["OSD"]["label_info"][0]["label_info_1"]["text"] == "unit test 2"
    assert result3["OSD"]["label_info"][0]["label_info_1"]["enabled"] == "off"

    result = tapo.getOsd()

    assert (
        result["OSD"]["label_info"][0]["label_info_1"]["text"]
        == origData["origLabelText"]
    )
    assert (
        result["OSD"]["label_info"][0]["label_info_1"]["enabled"]
        == origData["origLabelEnabled"]
    )
    assert (
        result["OSD"]["label_info"][0]["label_info_1"]["x_coor"]
        == origData["origLabelX"]
    )
    assert (
        result["OSD"]["label_info"][0]["label_info_1"]["y_coor"]
        == origData["origLabelY"]
    )
    assert result["OSD"]["date"]["enabled"] == origData["origDateEnabled"]
    assert result["OSD"]["date"]["x_coor"] == origData["origDateX"]
    assert result["OSD"]["date"]["y_coor"] == origData["origDateY"]
    assert result["OSD"]["week"]["enabled"] == origData["origWeekEnabled"]
    assert result["OSD"]["week"]["x_coor"] == origData["origWeekX"]
    assert result["OSD"]["week"]["y_coor"] == origData["origWeekY"]


def test_setOsd_failure():
    tapo = Tapo(host, user, password)

    originalOsd = tapo.getOsd()

    with pytest.raises(Exception) as err1:
        tapo.setOsd(
            "AAAAAAAAAAAAAAAAA",
            False,
            False,
            False,
            1,
            2,
            3,
            4,
            5,
            6,
        )

    with pytest.raises(Exception) as err2:
        tapo.setOsd(
            "valid label",
            False,
            False,
            False,
            -50,
            2,
            3,
            4,
            5,
            6,
        )

    with pytest.raises(Exception) as err3:
        tapo.setOsd(
            "valid label",
            False,
            False,
            False,
            1,
            10001,
            3,
            4,
            5,
            6,
        )

    # just in case something succeeded, restore original
    setOsd(tapo, originalOsd)
    assert "Error: Label cannot be longer than 16 characters" == str(err1.value)
    assert "Error: Incorrect corrdinates, must be between 0 and 10000" == str(
        err2.value
    )
    assert "Error: Incorrect corrdinates, must be between 0 and 10000" == str(
        err3.value
    )


def test_getModuleSpec():
    tapo = Tapo(host, user, password)
    result = tapo.getModuleSpec()
    assert "function" in result
    assert "module_spec" in result["function"]
    assert result["error_code"] == 0


def test_getPrivacyMode():
    tapo = Tapo(host, user, password)
    result = tapo.getPrivacyMode()
    assert result[".name"] == "lens_mask_info"
    assert result[".type"] == "lens_mask_info"
    assert "enabled" in result


def test_getMotionDetection():
    tapo = Tapo(host, user, password)
    result = tapo.getMotionDetection()
    assert result[".name"] == "motion_det"
    assert result[".type"] == "on_off"
    assert "enabled" in result
    assert "enhanced" in result
    assert "sensitivity" in result
    assert "digital_sensitivity" in result


def test_getAlarm():
    tapo = Tapo(host, user, password)
    result = tapo.getAlarm()
    assert result[".name"] == "chn1_msg_alarm_info"
    assert result[".type"] == "info"
    assert "enabled" in result
    assert "alarm_type" in result
    assert "alarm_mode" in result
    assert "light_type" in result


def test_getLED():
    tapo = Tapo(host, user, password)
    result = tapo.getLED()
    assert result[".name"] == "config"
    assert result[".type"] == "led"
    assert "enabled" in result


def test_getAutoTrackTarget():
    tapo = Tapo(host, user, password)
    result = tapo.getAutoTrackTarget()
    assert result[".name"] == "target_track_info"
    assert result[".type"] == "target_track_info"
    assert "enabled" in result


def test_getAudioSpec():
    tapo = Tapo(host, user, password)
    result = tapo.getAudioSpec()
    assert "audio_capability" in result
    assert "device_speaker" in result["audio_capability"]
    assert "device_microphone" in result["audio_capability"]
    assert result["error_code"] == 0


def test_getVhttpd():
    tapo = Tapo(host, user, password)
    result = tapo.getVhttpd()
    assert "cet" in result
    assert "vhttpd" in result["cet"]
    assert result["error_code"] == 0


def test_getTime():
    tapo = Tapo(host, user, password)
    result = tapo.getTime()
    assert "system" in result
    assert "clock_status" in result["system"]
    assert "seconds_from_1970" in result["system"]["clock_status"]
    assert "local_time" in result["system"]["clock_status"]
    assert result["error_code"] == 0


def test_getMotorCapability():
    tapo = Tapo(host, user, password)
    result = tapo.getMotorCapability()
    assert "motor" in result
    assert "capability" in result["motor"]
    assert result["error_code"] == 0


def test_setPrivacyMode():
    tapo = Tapo(host, user, password)
    result = tapo.getPrivacyMode()
    origEnabled = result["enabled"] == "on"
    tapo.setPrivacyMode(False)
    result = tapo.getPrivacyMode()
    assert result["enabled"] == "off"
    tapo.setPrivacyMode(True)
    result = tapo.getPrivacyMode()
    assert result["enabled"] == "on"
    tapo.setPrivacyMode(False)
    result = tapo.getPrivacyMode()
    assert result["enabled"] == "off"
    tapo.setPrivacyMode(origEnabled)


def test_setAlarm():
    tapo = Tapo(host, user, password)
    origAlarm = tapo.getAlarm()
    tapo.setAlarm(False)
    result = tapo.getAlarm()
    assert result["enabled"] == "off"
    tapo.setAlarm(True)
    result = tapo.getAlarm()
    assert result["enabled"] == "on"

    with pytest.raises(Exception) as err:
        result = tapo.setAlarm(False, False, False)
    assert "You need to use at least sound or light for alarm" in str(err.value)

    tapo.setAlarm(False, True, False)
    result = tapo.getAlarm()
    assert result["enabled"] == "off"
    assert "sound" in result["alarm_mode"]
    assert "light" not in result["alarm_mode"]

    tapo.setAlarm(True, False, True)
    result = tapo.getAlarm()
    assert result["enabled"] == "on"
    assert "sound" not in result["alarm_mode"]
    assert "light" in result["alarm_mode"]

    tapo.setAlarm(
        origAlarm["enabled"] == "on",
        "sound" in origAlarm["alarm_mode"],
        "light" in origAlarm["alarm_mode"],
    )


def test_moveMotor():
    tapo = Tapo(host, user, password)
    origPrivacyModeEnabled = tapo.getPrivacyMode()["enabled"] == "on"
    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(False)
    result = tapo.moveMotor(0, 0)
    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(True)
    assert result["error_code"] == 0


def test_moveMotorStep():
    tapo = Tapo(host, user, password)
    origPrivacyModeEnabled = tapo.getPrivacyMode()["enabled"] == "on"
    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(False)
    result1 = tapo.moveMotorStep(10)
    time.sleep(5)
    result2 = tapo.moveMotorStep(190)
    time.sleep(5)

    with pytest.raises(Exception) as err:
        tapo.moveMotorStep(360)
    assert "Angle must be in a range 0 <= angle < 360" in str(err.value)
    with pytest.raises(Exception) as err:
        tapo.moveMotorStep(-1)
    assert "Angle must be in a range 0 <= angle < 360" in str(err.value)

    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(True)
    assert result1["error_code"] == 0
    assert result2["error_code"] == 0


def test_calibrateMotor():
    tapo = Tapo(host, user, password)
    result = tapo.calibrateMotor()
    assert result["error_code"] == 0


def test_setLEDEnabled():
    tapo = Tapo(host, user, password)
    origLedEnabled = tapo.getLED()["enabled"] == "on"
    tapo.setLEDEnabled(True)
    result = tapo.getLED()
    assert result["enabled"] == "on"
    tapo.setLEDEnabled(False)
    result = tapo.getLED()
    assert result["enabled"] == "off"
    tapo.setLEDEnabled(True)
    result = tapo.getLED()
    assert result["enabled"] == "on"
    tapo.setLEDEnabled(origLedEnabled)
    result = tapo.getLED()
    assert (result["enabled"] == "on") == origLedEnabled


def test_getCommonImage():
    tapo = Tapo(host, user, password)
    result = tapo.getCommonImage()
    assert result["error_code"] == 0
    assert "image" in result
    assert "common" in result["image"]


def test_setDayNightMode():
    tapo = Tapo(host, user, password)
    origDayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    result = tapo.setDayNightMode("off")
    assert result["error_code"] == 0
    dayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    assert dayNightMode == "off"
    result = tapo.setDayNightMode("on")
    assert result["error_code"] == 0
    dayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    assert dayNightMode == "on"
    result = tapo.setDayNightMode("auto")
    assert result["error_code"] == 0
    dayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    assert dayNightMode == "auto"
    result = tapo.setDayNightMode("off")
    assert result["error_code"] == 0
    dayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    assert dayNightMode == "off"
    result = tapo.setDayNightMode(origDayNightMode)
    assert result["error_code"] == 0
    dayNightMode = tapo.getCommonImage()["image"]["common"]["inf_type"]
    assert dayNightMode == origDayNightMode
    with pytest.raises(Exception) as err:
        tapo.setDayNightMode("unsupported")
    assert "Invalid inf_type, can be off, on or auto" in str(err.value)


def test_setMotionDetection():
    tapo = Tapo(host, user, password)
    origMotionDetection = tapo.getMotionDetection()
    origMotionDetectionSensitivity = origMotionDetection["sensitivity"]
    if origMotionDetectionSensitivity == "medium":
        origMotionDetectionSensitivity = "normal"

    tapo.setMotionDetection(False)
    result = tapo.getMotionDetection()
    assert result["enabled"] == "off"
    tapo.setMotionDetection(True)
    result = tapo.getMotionDetection()
    assert result["enabled"] == "on"
    tapo.setMotionDetection(False)
    result = tapo.getMotionDetection()
    assert result["enabled"] == "off"
    tapo.setMotionDetection(False, "low")
    result = tapo.getMotionDetection()
    assert result["sensitivity"] == "low"
    tapo.setMotionDetection(False, "normal")
    result = tapo.getMotionDetection()
    assert result["sensitivity"] == "medium"
    tapo.setMotionDetection(False, "high")
    result = tapo.getMotionDetection()
    assert result["sensitivity"] == "high"

    with pytest.raises(Exception) as err:
        tapo.setMotionDetection(False, "unsupported")
    assert "Invalid sensitivity, can be low, normal or high" in str(err.value)

    tapo.setMotionDetection(
        origMotionDetection["enabled"] == "on", origMotionDetectionSensitivity
    )
    result = tapo.getMotionDetection()
    assert result["enabled"] == origMotionDetection["enabled"]
    assert result["sensitivity"] == origMotionDetection["sensitivity"]


def test_setAutoTrackTarget():
    tapo = Tapo(host, user, password)
    origAutoTrackEnabled = tapo.getAutoTrackTarget()["enabled"] == "on"
    tapo.setAutoTrackTarget(True)
    result = tapo.getAutoTrackTarget()
    assert result["enabled"] == "on"
    tapo.setAutoTrackTarget(False)
    result = tapo.getAutoTrackTarget()
    assert result["enabled"] == "off"
    tapo.setAutoTrackTarget(True)
    result = tapo.getAutoTrackTarget()
    assert result["enabled"] == "on"

    tapo.setAutoTrackTarget(origAutoTrackEnabled)
    result = tapo.getAutoTrackTarget()
    assert (result["enabled"] == "on") == origAutoTrackEnabled


def test_errorMessage():
    tapo = Tapo(host, user, password)
    origPrivacyModeEnabled = tapo.getPrivacyMode()["enabled"] == "on"
    if not origPrivacyModeEnabled:
        tapo.setPrivacyMode(True)
    with pytest.raises(Exception) as err:
        tapo.savePreset("unit test")
    assert "Privacy mode is ON, not able to execute" in str(err.value)
    if not origPrivacyModeEnabled:
        tapo.setPrivacyMode(False)


def test_preset():
    tapo = Tapo(host, user, password)
    origPrivacyModeEnabled = tapo.getPrivacyMode()["enabled"] == "on"
    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(False)
    result = tapo.savePreset("unit test")
    assert result is True

    presets = tapo.getPresets()
    idToSet = list(presets.keys())[list(presets.values()).index("unit test")]
    result = tapo.setPreset(idToSet)
    assert result["error_code"] == 0

    with pytest.raises(Exception) as err:
        tapo.setPreset(-2)
    assert "Preset -2 is not set in the app" in str(err.value)

    while True:
        try:
            presets = tapo.getPresets()
            idToDelete = list(presets.keys())[list(presets.values()).index("unit test")]
            result = tapo.deletePreset(idToDelete)
            assert result is True
        except Exception as e:
            assert "'unit test' is not in list" in str(e)
            break

    with pytest.raises(Exception) as err:
        tapo.deletePreset(-1)
    assert "Preset -1 is not set in the app" in str(err.value)

    if origPrivacyModeEnabled:
        tapo.setPrivacyMode(True)


def test_reboot():
    tapo = Tapo(host, user, password)
    result = tapo.reboot()
    assert result["error_code"] == 0


def test_no_presets():
    with mock.patch.object(Tapo, "getPresets", new=getPresetsMock):
        tapo = Tapo(host, user, password)
        tapo.refreshStok()

    assert tapo.presets == {}
