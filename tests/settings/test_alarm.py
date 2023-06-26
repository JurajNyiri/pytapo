import pytest
from unittest.mock import MagicMock
from pytapo.error import AlarmException
from pytapo.settings.alarm import AlarmInterface


@pytest.fixture
def execute_function():
    return MagicMock()


@pytest.fixture
def perform_request():
    return MagicMock()


@pytest.fixture
def alarm_interface(perform_request, execute_function):
    child_id = None
    return AlarmInterface(execute_function, perform_request, child_id)


def test_manual_alarm_start(alarm_interface):
    alarm_interface.start_manual_alarm()
    alarm_interface.perform_request.assert_called_once_with(
        {
            "method": "do",
            "msg_alarm": {"manual_msg_alarm": {"action": "start"}},
        }
    )


def test_manual_alarm_stop(alarm_interface):
    alarm_interface.stop_manual_alarm()
    alarm_interface.perform_request.assert_called_once_with(
        {
            "method": "do",
            "msg_alarm": {"manual_msg_alarm": {"action": "stop"}},
        }
    )


def test_set_alarm_raises_exception_when_no_sound_light(alarm_interface):
    with pytest.raises(AlarmException):
        alarm_interface.set_alarm(True, False, False)


def test_set_alarm(mocker, alarm_interface):
    mocker.patch.object(alarm_interface, "perform_request", return_value=None)
    alarm_interface.set_alarm(True, True, True)
    alarm_interface.perform_request.assert_called_once_with(
        {
            "method": "set",
            "msg_alarm": {
                "chn1_msg_alarm_info": {
                    "enabled": "on",
                    "alarm_mode": ["sound", "light"],
                    "alarm_type": "0",
                    "light_type": "0",
                }
            },
        }
    )


def test_get_alarm(mocker, alarm_interface):
    expected_alarm_config = {
        "alarm_mode": ["sound"],
        "enabled": "on",
        "alarm_type": "0",
        "light_type": "0",
        "msg_alarm": {
            "chn1_msg_alarm_info": {
                "alarm_mode": ["sound"],
                "enabled": "on",
                "alarm_type": "0",
                "light_type": "0",
            }
        },
    }
    mocker.patch.object(alarm_interface, "execute", return_value=expected_alarm_config)
    alarm_config = alarm_interface.get_alarm()
    assert alarm_config == {'alarm_mode': ['sound'], 'enabled': 'on', 'alarm_type': '0', 'light_type': '0'}


def test_get_alarm_config(alarm_interface):
    expected_config = {
        "requests": [
            {"method": "getAlarmConfig", "params": {"msg_getalarmconfig": {}}},
            {"method": "getAlarmPlan", "params": {"msg_getalarmplan": {}}},
            {"method": "getSirenTypeList", "params": {"msg_getsirentypelist": {}}},
            {"method": "getLightTypeList", "params": {"msg_getlighttypelist": {}}},
            {"method": "getSirenStatus", "params": {"msg_getsirenstatus": {}}},
        ]
    }
    alarm_interface.execute.return_value = expected_config
    alarm_config = alarm_interface.get_alarm_config()
    assert alarm_config == expected_config
