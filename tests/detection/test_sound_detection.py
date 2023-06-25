import pytest
from unittest.mock import Mock
from pytapo.detection.sound_detection import AudioDetection
from pytapo.error import DetectionSensitivityNotSupportedException


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
def audio_detection(mock_request, mock_execute):
    return AudioDetection(mock_execute, mock_request, "dummy_child_id")


def test_setBabyCryDetection(audio_detection):
    audio_detection.setBabyCryDetection(True, "high")
    audio_detection.execute_function.assert_called_once_with(
        "setBCDConfig",
        {"sound_detection": {"bcd": {"enabled": "on", "sensitivity": "80"}}},
    )


def test_getBabyCryDetection(audio_detection):
    response = {"sound_detection": {"bcd": {"enabled": "on"}}}
    audio_detection.execute_function = Mock(return_value=response)
    result = audio_detection.getBabyCryDetection()
    assert result == {"enabled": "on"}


def test_setMeowDetection(audio_detection):
    audio_detection.setMeowDetection(True, "low")
    audio_detection.execute_function.assert_called_once_with(
        "setMeowDetectionConfig",
        {"meow_detection": {"detection": {"enabled": "on", "sensitivity": "20"}}},
    )


def test_getMeowDetection(audio_detection):
    response = {"meow_detection": {"detection": {"enabled": "on"}}}
    audio_detection.execute_function = Mock(return_value=response)
    result = audio_detection.getMeowDetection()
    assert result == {"enabled": "on"}


def test_setGlassBreakDetection(audio_detection):
    audio_detection.setGlassBreakDetection(True, "normal")
    audio_detection.execute_function.assert_called_once_with(
        "setGlassDetectionConfig",
        {"glass_detection": {"detection": {"enabled": "on", "sensitivity": "50"}}},
    )


def test_getGlassBreakDetection(audio_detection):
    response = {"glass_detection": {"detection": {"enabled": "on"}}}
    audio_detection.execute_function = Mock(return_value=response)
    result = audio_detection.getGlassBreakDetection()
    assert result == {"enabled": "on"}


def test_setTamperDetection(audio_detection):
    audio_detection.setTamperDetection(True, "low")
    audio_detection.execute_function.assert_called_once_with(
        "setTamperDetectionConfig",
        {"tamper_detection": {"tamper_det": {"enabled": "on", "sensitivity": "20"}}},
    )


def test_getTamperDetection(audio_detection):
    response = {"tamper_detection": {"tamper_det": {"enabled": "on"}}}
    audio_detection.execute_function = Mock(return_value=response)
    result = audio_detection.getTamperDetection()
    assert result == {"enabled": "on"}


def test_invalid_sensitivity(audio_detection):
    with pytest.raises(DetectionSensitivityNotSupportedException):
        audio_detection.setBabyCryDetection(True, "invalid")
