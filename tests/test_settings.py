import pytest
from pytapo import PyTapo


@pytest.fixture
def tapo_cam():
    return PyTapo("YourHost", "YourUser", "YourPass")


def test_get_set_timezone(tapo_cam):
    # Add your test logic here
    original_timezone = tapo_cam.get_timezone()
    assert isinstance(original_timezone, str)

    tapo_cam.set_timezone("GMT")
    assert tapo_cam.get_timezone() == "GMT"

    # Reset to original timezone after the test
    tapo_cam.set_timezone(original_timezone)


def test_get_set_privacy_mode(tapo_cam):
    original_mode = tapo_cam.get_privacy_mode()
    assert isinstance(original_mode, bool)

    tapo_cam.set_privacy_mode(not original_mode)
    assert tapo_cam.get_privacy_mode() == (not original_mode)

    # Reset to original mode after the test
    tapo_cam.set_privacy_mode(original_mode)


def test_get_set_flip(tapo_cam):
    original_flip = tapo_cam.get_flip()
    assert isinstance(original_flip, bool)

    tapo_cam.set_flip(not original_flip)
    assert tapo_cam.get_flip() == (not original_flip)

    # Reset to original flip state after the test
    tapo_cam.set_flip(original_flip)


def test_get_set_night_mode(tapo_cam):
    original_mode = tapo_cam.get_night_mode()
    assert isinstance(original_mode, bool)

    tapo_cam.set_night_mode(not original_mode)
    assert tapo_cam.get_night_mode() == (not original_mode)

    # Reset to original mode after the test
    tapo_cam.set_night_mode(original_mode)


def test_get_set_alarm(tapo_cam):
    original_alarm = tapo_cam.get_alarm()
    assert isinstance(original_alarm, bool)

    tapo_cam.set_alarm(not original_alarm)
    assert tapo_cam.get_alarm() == (not original_alarm)

    # Reset to original alarm state after the test
    tapo_cam.set_alarm(original_alarm)


def test_get_set_led(tapo_cam):
    original_led = tapo_cam.get_led()
    assert isinstance(original_led, bool)

    tapo_cam.set_led(not original_led)
    assert tapo_cam.get_led() == (not original_led)

    # Reset to original led state after the test
    tapo_cam.set_led(original_led)


def test_get_set_auto_track(tapo_cam):
    original_auto_track = tapo_cam.get_auto_track()
    assert isinstance(original_auto_track, bool)

    tapo_cam.set_auto_track(not original_auto_track)
    assert tapo_cam.get_auto_track() == (not original_auto_track)

    # Reset to original auto track state after the test
    tapo_cam.set_auto_track(original_auto_track)


def test_get_set_motor(tapo_cam):
    original_motor = tapo_cam.get_motor()
    assert isinstance(original_motor, bool)

    tapo_cam.set_motor(not original_motor)
    assert tapo_cam.get_motor() == (not original_motor)

    # Reset to original motor state after the test
    tapo_cam.set_motor(original_motor)


def test_get_set_video_enc(tapo_cam):
    original_video_enc = tapo_cam.get_video_enc()
    assert isinstance(original_video_enc, str)

    # Replace "YourVideoEnc" with the video encoding you want to test
    tapo_cam.set_video_enc("YourVideoEnc")
    assert tapo_cam.get_video_enc() == "YourVideoEnc"

    # Reset to original video encoding after the test
    tapo_cam.set_video_enc(original_video_enc)
