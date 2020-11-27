import os
import pytest
import json
from pytapo import Tapo

user = os.environ.get("PYTAPO_USER")
password = os.environ.get("PYTAPO_PASSWORD")
invalidPassword = "{password}_invalid".format(password=password)
host = os.environ.get("PYTAPO_IP")


def setOsd(tapo, values):
    data = {
        "origLabelText": values["OSD"]["label_info"][0]["label_info_1"]["text"],
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


def test_refreshStok_success():
    tapo = Tapo(host, user, password)
    result = tapo.refreshStok()
    assert isinstance(result, str)


def test_refreshStok_failure():
    with pytest.raises(Exception) as err:
        tapo = Tapo(host, user, invalidPassword)
        tapo.refreshStok()
    assert "Invalid authentication data." in str(err.value)


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

    assert "text" not in result3["OSD"]["label_info"][0]["label_info_1"]
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
    assert "Error: Label cannot be longer than 16 characters." == str(err1.value)
    assert "Error: Incorrect corrdinates, must be between 0 and 10000." == str(
        err2.value
    )
    assert "Error: Incorrect corrdinates, must be between 0 and 10000." == str(
        err3.value
    )


def test_getModuleSpec():
    tapo = Tapo(host, user, password)
    result = tapo.getModuleSpec()
    print(result)
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
