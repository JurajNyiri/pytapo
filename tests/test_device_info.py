import pytest
from pytapo import PyTapo


# Function to setup a fixture, replace 'YourHost', 'YourUser', 'YourPass' with actual values
@pytest.fixture
def tapo_cam():
    return PyTapo("YourHost", "YourUser", "YourPass")


def test_get_device_info(tapo_cam):
    # Add your test logic here
    # For instance, if get_device_info() returns a dict with device information
    device_info = tapo_cam.get_device_info()

    assert isinstance(device_info, dict)
    # Check for some specific keys in the device info dictionary
    assert "mac" in device_info
    assert "model" in device_info
    assert "name" in device_info
