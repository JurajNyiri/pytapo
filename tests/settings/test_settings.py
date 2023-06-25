import pytest
from unittest.mock import MagicMock, Mock
from pytapo.settings import DeviceInterface


@pytest.fixture
def mock_request():
    mock = Mock()
    mock.return_value = {"success": True}
    return mock


@pytest.fixture
def mock_execute():
    mock = Mock()
    mock.return_value = {"success": True}
    return mock


def execute_and_assert(
    mock_execute,
    device_interface,
    method,
    return_value=None,
    call_value=None,
    expected_result=None,
):
    if return_value is not None:
        mock_execute.return_value = return_value
    assert getattr(device_interface, method)(call_value) == expected_result
    if return_value is not None:
        mock_execute.assert_called_once_with(method, return_value)


@pytest.fixture
def device_interface(mock_execute, mock_request):
    device_interface = DeviceInterface(mock_execute, mock_request, None)
    device_interface.execute_function = mock_request
    device_interface.perform_request = mock_execute
    return device_interface


def test_set_privacy_mode(device_interface, mock_execute, mock_request):
    execute_and_assert(
        mock_execute,
        device_interface,
        "setPrivacyMode",
        return_value={"success": True},
        call_value=True,
        expected_result={"success": True},
    )


def test_get_privacy_mode(device_interface, mock_execute, mock_request):
    execute_and_assert(
        mock_execute,
        device_interface,
        "getPrivacyMode",
        return_value={"lens_mask": {"lens_mask_info": {"enabled": "on"}}},
        expected_result={"enabled": "on"},
    )


def test_set_media_encrypt(device_interface, mock_execute, mock_request):
    execute_and_assert(
        mock_execute,
        device_interface,
        "setMediaEncrypt",
        return_value={"success": True},
        call_value=True,
        expected_result={"success": True},
    )


def test_get_media_encrypt(device_interface, mock_execute, mock_request):
    execute_and_assert(
        mock_execute,
        device_interface,
        "getMediaEncrypt",
        return_value={"cet": {"media_encrypt": {"enabled": "on"}}},
        expected_result={"enabled": "on"},
    )


def test_get_rotation_status(device_interface, mock_execute, mock_request):
    execute_and_assert(
        mock_execute,
        device_interface,
        "getRotationStatus",
        return_value={"image": {"switch": "on"}},
        expected_result={"image": {"switch": "on"}},
    )


def test_get_auto_track_target(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {
        "target_track": {"target_track_info": {"enabled": "on"}}
    }
    assert device_interface.getAutoTrackTarget() == {"enabled": "on"}
    mock_execute.assert_called_once_with(
        "getTargetTrackConfig", {"target_track": {"name": ["target_track_info"]}}
    )


def test_get_audio_spec(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {"audio_capability": {"device_speaker": "on"}}
    assert device_interface.getAudioSpec() == {
        "audio_capability": {"device_speaker": "on"}
    }
    mock_execute.assert_called_once_with(
        "getAudioCapability", {"audio_capability": {"name": ["device_speaker"]}}
    )


def test_get_vhttpd(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {"cet": {"vhttpd": "on"}}
    assert device_interface.getVhttpd() == {"cet": {"vhttpd": "on"}}
    mock_execute.assert_called_once_with("getVhttpd", {"cet": {"name": ["vhttpd"]}})


def test_get_basic_info(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {"device_info": {"basic_info": {"model": "test_model"}}}
    assert device_interface.getBasicInfo() == {
        "device_info": {"basic_info": {"model": "test_model"}}
    }


def test_get_time(device_interface, mock_execute, mock_request):
    mock_request.return_value = {"system": {"clock_status": {"current_time": "12:00"}}}
    mock_execute.return_value = {"system": {"clock_status": {"current_time": "12:00"}}}
    assert device_interface.getTime() == {
        "system": {"clock_status": {"current_time": "12:00"}}
    }
    mock_execute.assert_called_once_with(
        "getClockStatus", {"system": {"name": "clock_status"}}
    )


def test_get_osd(device_interface, mock_execute, mock_request):
    mock_request.return_value = {"OSD": {"date": {"enabled": "on"}}}
    mock_execute.return_value = {"OSD": {"date": {"enabled": "on"}}}
    assert device_interface.getOsd() == {"OSD": {"date": {"enabled": "on"}}}
    mock_execute.assert_called_once_with(
        "getOsd", {"OSD": {"name": ["date", "week", "font"], "table": ["label_info"]}}
    )


def test_set_osd(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {"success": True}
    device_interface.setOsd("test_label")
    mock_execute.assert_called_once_with(
        {
            "method": "set",
            "OSD": {
                "date": {"enabled": "on", "x_coor": 0, "y_coor": 0},
                "week": {"enabled": "off", "x_coor": 0, "y_coor": 0},
                "font": {
                    "color": "white",
                    "color_type": "auto",
                    "display": "ntnb",
                    "size": "auto",
                },
                "label_info_1": {
                    "enabled": "off",
                    "x_coor": 0,
                    "y_coor": 500,
                    "text": "test_label",
                },
            },
        }
    )


def test_get_module_spec(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {"module_spec": {"module_1": "active"}}
    assert device_interface.getModuleSpec() == {"module_spec": {"module_1": "active"}}


def test_get_child_devices(device_interface, mock_execute, mock_request):
    mock_execute.return_value = {
        "result": {"child_device_list": ["child_1", "child_2"]}
    }
    assert device_interface.getChildDevices() == ["child_1", "child_2"]


def test_get_time_correction(device_interface, mock_execute, mock_request):
    mock_execute.return_value = False
    assert device_interface.getTimeCorrection() is False


def test_get_events(device_interface, mock_execute, mock_request):
    device_interface.getTimeCorrection.return_value = True
    mock_execute.return_value = {
        "playback": {"search_detection_list": [{"event": "event_1"}]}
    }
    assert device_interface.getEvents() == [{"event": "event_1"}]
