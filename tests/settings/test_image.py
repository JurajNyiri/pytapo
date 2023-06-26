import pytest
from unittest.mock import MagicMock
from pytapo.settings.image import ImageInterface


@pytest.fixture
def image_interface_no_child():
    execute_function = MagicMock()
    perform_request = MagicMock()
    return ImageInterface(perform_request, execute_function, None)


@pytest.fixture
def image_interface():
    execute_function = MagicMock()
    perform_request = MagicMock()
    child_id = "123"
    return ImageInterface(perform_request, execute_function, child_id)


def test_set_day_night_mode_child_id(image_interface):
    image_interface.set_day_night_mode("on")
    image_interface.execute_function.assert_called_once_with(
        "setNightVisionModeConfig",
        {"image": {"switch": {"night_vision_mode": "inf_night_vision"}}},
    )


def test_get_image_flip_vertical_child_id(image_interface):
    image_interface.execute_function.return_value = {
        "image": {"switch": {"flip_type": "center"}}
    }
    assert image_interface.get_image_flip_vertical() == True
    image_interface.execute_function.assert_called_once_with(
        "getRotationStatus", {"image": {"name": "switch"}}
    )


def test_set_image_flip_vertical_child_id(image_interface):
    image_interface.set_image_flip_vertical(True)
    image_interface.execute_function.assert_called_once_with(
        "setRotationStatus",
        {"image": {"switch": {"flip_type": "center"}}},
    )


def test_set_lens_distortion_correction(image_interface):
    image_interface.set_lens_distortion_correction(True)
    image_interface.execute_function.assert_called_once_with(
        "setLdc", {"image": {"switch": {"ldc": "on"}}}
    )


def test_get_lens_distortion_correction(image_interface):
    image_interface.execute_function.return_value = {"image": {"switch": {"ldc": "on"}}}
    assert image_interface.get_lens_distortion_correction() is True
    image_interface.execute_function.assert_called_once_with(
        "getLdc", {"image": {"name": ["switch"]}}
    )


def test_get_day_night_mode(image_interface):
    image_interface.execute_function.return_value = {
        "image": {"switch": {"night_vision_mode": "inf_night_vision"}}
    }
    assert image_interface.get_day_night_mode() == "on"


def test_set_day_night_mode(image_interface):
    image_interface.set_day_night_mode("on")
    image_interface.execute_function.assert_called_once_with(
        "setNightVisionModeConfig",
        {"image": {"switch": {"night_vision_mode": "inf_night_vision"}}},
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
    image_interface.execute_function.return_value = {
        "image": {"switch": {"flip_type": "center"}}
    }
    assert image_interface.get_image_flip_vertical() is True
    image_interface.execute_function.assert_called_once_with(
        "getRotationStatus", {"image": {"name": "switch"}}
    )


def test_set_image_flip_vertical(image_interface):
    image_interface.set_image_flip_vertical(True)
    image_interface.execute_function.assert_called_once_with(
        "setRotationStatus", {"image": {"switch": {"flip_type": "center"}}}
    )


def test_get_force_whitelamp_state(image_interface):
    image_interface.execute_function.return_value = {
        "image": {"switch": {"force_wtl_state": "on"}}
    }
    assert image_interface.get_force_whitelamp_state() is True
    image_interface.execute_function.assert_called_once_with(
        "getLdc", {"image": {"name": ["switch"]}}
    )


def test_set_force_whitelamp_state(image_interface):
    image_interface.set_force_whitelamp_state(True)
    image_interface.execute_function.assert_called_once_with(
        "setLdc", {"image": {"switch": {"force_wtl_state": "on"}}}
    )
