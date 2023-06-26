import pytest
from unittest.mock import MagicMock
from pytapo.error import LightFrequencyModeNotSupportedException
from pytapo.settings.led import LEDInterface


@pytest.fixture
def led_interface():
    mock_execute = MagicMock()
    mock_request = MagicMock()
    return LEDInterface(mock_request, mock_execute)


def test_get_light_frequency_mode(led_interface):
    led_interface.execute_function.return_value = {"status": "success"}
    light_frequency_mode = led_interface.get_light_frequency_mode()
    assert light_frequency_mode == {"status": "success"}
    led_interface.execute_function.assert_called_once_with("getLightFrequencyMode", {})


def test_set_light_frequency_mode_valid(led_interface):
    led_interface.execute_function.return_value = {"status": "success"}
    assert led_interface.set_light_frequency_mode("50") == {"status": "success"}
    led_interface.execute_function.assert_called_once_with(
        "setLightFrequencyMode", {"mode": "50"}
    )


def test_set_led_enabled(led_interface):
    led_interface.execute_function.return_value = {"status": "success"}
    assert led_interface.set_led_enabled(True) == {"status": "success"}
    led_interface.execute_function.assert_called_once_with(
        "setLedStatus", {"led": {"config": {"enabled": "on"}}}
    )


def test_get_led(led_interface):
    led_interface.execute_function.return_value = {
        "led": {"config": {".name": "config", ".type": "led", "enabled": "on"}}
    }
    expected_result = {".name": "config", ".type": "led", "enabled": "on"}
    assert led_interface.getLED() == expected_result
    led_interface.execute_function.assert_called_once_with(
        "getLedStatus", {"led": {"name": ["config"]}}
    )
