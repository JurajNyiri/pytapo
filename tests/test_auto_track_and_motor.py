import time
import pytest
from pytapo import PyTapo


# Function to setup a fixture, replace 'YourHost', 'YourUser', 'YourPass' with actual values
@pytest.fixture
def tapo_cam():
    return PyTapo("YourHost", "YourUser", "YourPass")


# Teardown function
def teardown_function(tapo_cam):
    # Here you can add commands to restore your device settings to their original state after tests
    tapo_cam.set_auto_track(False)
    tapo_cam.set_motor(False)
    tapo_cam.setPrivacyMode(True)


@pytest.mark.parametrize(
    "value, expected", [(True, {"auto_track": True}), (False, {"auto_track": False})]
)
def test_set_get_auto_track(tapo_cam, value, expected):
    assert tapo_cam.set_auto_track(value) == expected
    assert tapo_cam.get_auto_track() == expected


@pytest.mark.parametrize(
    "value, expected", [(True, {"motor": True}), (False, {"motor": False})]
)
def test_set_get_motor(tapo_cam, value, expected):
    assert tapo_cam.set_motor(value) == expected
    assert tapo_cam.get_motor() == expected


def test_move_motor_vertical(tapo_cam):
    orig_privacy_mode_enabled = tapo_cam.getPrivacyMode()["enabled"] == "on"
    if orig_privacy_mode_enabled:
        tapo_cam.setPrivacyMode(False)

    result = tapo_cam.moveMotorVertical()
    time.sleep(5)

    if orig_privacy_mode_enabled:
        tapo_cam.setPrivacyMode(True)

    assert result["error_code"] == 0


def test_move_motor_horizontal(tapo_cam):
    orig_privacy_mode_enabled = tapo_cam.getPrivacyMode()["enabled"] == "on"
    if orig_privacy_mode_enabled:
        tapo_cam.setPrivacyMode(False)

    result = tapo_cam.moveMotorHorizontal()
    time.sleep(5)

    if orig_privacy_mode_enabled:
        tapo_cam.setPrivacyMode(True)

    assert result["error_code"] == 0
