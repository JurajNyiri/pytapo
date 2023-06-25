import pytest
from unittest.mock import Mock
from pytapo.error import LightFrequencyModeNotSupportedException
from pytapo.settings import LEDInterface


@pytest.fixture
def mock_execute():
    mock = Mock()
    mock.side_effect = lambda *args, **kwargs: {"status": "success"}
    return mock


@pytest.fixture
def mock_request():
    mock = Mock()
    mock.side_effect = lambda *args, **kwargs: {"status": "success"}
    return mock


@pytest.fixture
def led_interface(mock_request, mock_execute):
    return LEDInterface(mock_execute, mock_request)


def test_get_light_frequency_mode(led_interface, mock_execute):
    mock_execute.return_value = {"status": "success"}
    led_interface.execute_function = mock_execute
    light_frequency_mode = led_interface.get_light_frequency_mode()
    assert light_frequency_mode == {"status": "success"}
    mock_execute.assert_called_once_with("getLightFrequencyMode")


def test_set_light_frequency_mode_valid(led_interface, mock_execute):
    mock_execute.return_value = {"status": "success"}
    led_interface.execute_function = mock_execute
    assert led_interface.set_light_frequency_mode("50") == {"status": "success"}
    mock_execute.assert_called_once_with("setLightFrequencyMode", {"mode": "50"})


def test_set_led_enabled(led_interface, mock_execute):
    mock_execute.return_value = {"status": "success"}
    led_interface.execute_function = mock_execute
    assert led_interface.set_led_enabled(True) == {"status": "success"}
    mock_execute.assert_called_once_with(
        "setLedStatus", {"led": {"config": {"enabled": "on"}}}
    )


def test_get_led(led_interface, mock_execute):
    # update return value to match actual function output
    mock_execute.return_value = {
        "led": {"config": {".name": "config", ".type": "led", "enabled": "on"}}
    }
    led_interface.execute_function = mock_execute

    # since getLED method directly returns the output from execute_function,
    # the expected result would be the return value of the mocked function
    expected_result = {".name": "config", ".type": "led", "enabled": "on"}
    assert led_interface.getLED() == expected_result
    mock_execute.assert_called_once_with("getLedStatus", {"led": {"name": ["config"]}})
