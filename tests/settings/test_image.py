import pytest
from unittest.mock import Mock
from pytapo.error import (
    ImageCommonNotSupportedException,
    DayNightModeNotSupportedException,
)
from pytapo.settings import ImageInterface


@pytest.fixture
def image_interface():
    execute_function = Mock()
    execute_function.return_value = {
        "image": {
            "switch": {"ldc": "on", "flip_type": "center", "force_wtl_state": "on"}
        }
    }
    perform_request = Mock()
    perform_request.return_value = {"method": "get", "image": {"name": "common"}}  # Adjusted return value to match expected output
    child_id = "123"
    return ImageInterface(execute_function, perform_request, child_id)


def test_get_lens_distortion_correction(image_interface):
    assert image_interface.get_lens_distortion_correction() == True
    image_interface.execute_function.assert_called_once_with(
        "getLdc", {"image": {"name": ["switch"]}}
    )


def test_set_lens_distortion_correction(image_interface):
    image_interface.set_lens_distortion_correction(True)
    image_interface.execute_function.assert_called_once_with(
        "setLdc", {"image": {"switch": {"ldc": "on"}}}
    )


def test_get_day_night_mode(image_interface):
    image_interface.execute_function.return_value = {
        "image": {"common": {"inf_type": "on"}}
    }
    assert image_interface.get_day_night_mode() == "on"
    image_interface.execute_function.assert_called_once_with(
        "getLightFrequencyInfo", {"image": {"name": "common"}}
    )


def test_set_day_night_mode(image_interface):
    image_interface.set_day_night_mode("on")
    image_interface.execute_function.assert_called_once_with(
        "setLightFrequencyInfo", {"image": {"common": {"inf_type": "on"}}}
    )


def test_get_night_vision_mode_config(image_interface):
    image_interface.get_night_vision_mode_config()
    image_interface.execute_function.assert_called_once_with(
        "getNightVisionModeConfig", {"image": {"name": "switch"}}
    )


def test_set_night_vision_mode_config(image_interface):
    image_interface.set_night_vision_mode_config("inf_night_vision")
    image_interface.execute_function.assert_called_once_with(
        "setNightVisionModeConfig",
        {"image": {"switch": {"night_vision_mode": "inf_night_vision"}}},
    )


def test_get_image_flip_vertical(image_interface):
    assert image_interface.get_image_flip_vertical() == True
    image_interface.execute_function.assert_called_once_with(
        "getLdc", {"image": {"name": ["switch"]}}
    )


def test_set_image_flip_vertical(image_interface):
    image_interface.set_image_flip_vertical(True)
    image_interface.execute_function.assert_called_once_with(
        "setLdc", {"image": {"switch": {"flip_type": "center"}}}
    )


def test_get_force_whitelamp_state(image_interface):
    assert image_interface.get_force_whitelamp_state() is True
    image_interface.execute_function.assert_called_once_with(
        "getLdc", {"image": {"name": ["switch"]}}
    )


def test_set_force_whitelamp_state(image_interface):
    image_interface.set_force_whitelamp_state(True)
    image_interface.execute_function.assert_called_once_with(
        "setLdc", {"image": {"switch": {"force_wtl_state": "on"}}}
    )


def test_get_common_image(image_interface):
    expected_response = {"method": "get", "image": {"name": "common"}}  # This is the response we expect from get_common_image()
    assert image_interface.get_common_image() == expected_response
    image_interface.perform_request.assert_called_once_with(
        {"method": "get", "image": {"name": "common"}}
    )
