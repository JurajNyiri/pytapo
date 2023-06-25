import pytest
from pytapo import PyTapo


@pytest.fixture
def tapo_cam():
    return PyTapo("YourHost", "YourUser", "YourPass")


def test_get_sdcard_info(tapo_cam):
    sdcard_info = tapo_cam.get_sdcard_info()
    # Here, make assertions based on your expected structure of the sdcard_info object.
    # For example, if sdcard_info should be a dictionary with certain keys, you can test that:
    assert isinstance(sdcard_info, dict)
    assert "capacity" in sdcard_info
    assert "free_space" in sdcard_info
    assert "status" in sdcard_info


def test_format_sdcard(tapo_cam):
    # Make sure to handle this carefully, as it can erase data on the SD card.
    # Here's a basic example:

    result = tapo_cam.format_sdcard()

    # Assuming format_sdcard returns a success message, you can check for it:
    assert result == "Format Successful"

    # After a successful format, you might want to check the sdcard_info again:
    sdcard_info = tapo_cam.get_sdcard_info()
    assert sdcard_info["free_space"] == sdcard_info["capacity"]
