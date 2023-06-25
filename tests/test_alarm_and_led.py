import pytest
from pytapo import PyTapo


# Function to setup a fixture, replace 'YourHost', 'YourUser', 'YourPass' with actual values
@pytest.fixture
def tapo_cam():
    return PyTapo("YourHost", "YourUser", "YourPass")


def test_get_alarm(tapo_cam):
    # Add your test logic here
    # For instance, if get_alarm() returns a dict {'alarm': True} when alarm is on
    assert tapo_cam.get_alarm() == {"alarm": True}


def test_set_alarm(tapo_cam):
    # Add your test logic here
    # For instance, if set_alarm() returns a dict {'alarm': True} when alarm is successfully set
    assert tapo_cam.set_alarm(True) == {"alarm": True}


def test_get_led(tapo_cam):
    # Add your test logic here
    # For instance, if get_led() returns a dict {'led': True} when led is on
    assert tapo_cam.get_led() == {"led": True}


def test_set_led(tapo_cam):
    # Add your test logic here
    # For instance, if set_led() returns a dict {'led': True} when led is successfully set
    assert tapo_cam.set_led(True) == {"led": True}


def test_set_led(tapo_cam):
    orig_led_enabled = tapo_cam.getLED()["enabled"] == "on"
    tapo_cam.setLEDEnabled(True)

    result = tapo_cam.getLED()
    assert result["enabled"] == "on"

    tapo_cam.setLEDEnabled(False)
    result = tapo_cam.getLED()
    assert result["enabled"] == "off"

    tapo_cam.setLEDEnabled(True)
    result = tapo_cam.getLED()
    assert result["enabled"] == "on"

    tapo_cam.setLEDEnabled(orig_led_enabled)
    result = tapo_cam.getLED()
    assert (result["enabled"] == "on") == orig_led_enabled