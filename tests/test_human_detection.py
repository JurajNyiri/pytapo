import pytest
from pytapo import Tapo


@pytest.fixture
def tapo_cam():
    return Tapo("YourHost", "YourUser", "YourPass")


def test_get_set_human_detection(tapo_cam):
    original_setting = tapo_cam.get_human_detection()
    assert isinstance(original_setting, bool)

    tapo_cam.set_human_detection(not original_setting)
    assert tapo_cam.get_human_detection() == (not original_setting)

    # Reset to original setting after the test
    tapo_cam.set_human_detection(original_setting)
