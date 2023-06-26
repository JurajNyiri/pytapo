import pytest
from unittest.mock import Mock
from pytapo.detection.detection import DetectionInterface
from pytapo.error import DetectionException, DetectionSensitivityNotSupportedException


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
def detection(mock_request, mock_execute):
    return DetectionInterface(mock_execute, mock_request, "dummy_child_id")


def test_get_sensitivity_number(detection):
    assert detection._DetectionInterface__getSensitivityNumber("50") == "50"
    assert detection._DetectionInterface__getSensitivityNumber("high") == "80"
    assert detection._DetectionInterface__getSensitivityNumber("normal") == "50"
    assert detection._DetectionInterface__getSensitivityNumber("low") == "20"
    with pytest.raises(DetectionSensitivityNotSupportedException):
        detection._DetectionInterface__getSensitivityNumber("invalid")


def test_set_motion_detection(detection):
    response = detection.setMotionDetection(True, "high")
    assert response["status"] == "success"


def test_set_auto_track_target(detection):
    response = detection.setAutoTrackTarget(True)
    assert response["status"] == "success"


def test_set_cruise(detection):
    response = detection.setCruise(True, "x")
    assert response["status"] == "success"
    with pytest.raises(DetectionException):
        detection.setCruise(True, "invalid")


def test_set_person_detection(detection):
    response = detection.setPersonDetection(True, "low")
    assert response["status"] == "success"


def test_set_vehicle_detection(detection):
    response = detection.setVehicleDetection(True, "normal")
    assert response["status"] == "success"


def test_set_pet_detection(detection):
    response = detection.setPetDetection(True, "high")
    assert response["status"] == "success"


def test_set_detection_configuration(detection):
    response = detection.setDetectionConfiguration(
        "people_detection", True, "50", "setPersonDetectionConfig"
    )
    assert response["status"] == "success"
    with pytest.raises(DetectionSensitivityNotSupportedException):
        detection.setDetectionConfiguration(
            "people_detection", True, "invalid", "setPersonDetectionConfig"
        )
