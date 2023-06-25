import pytest
from unittest.mock import Mock, patch
from pytapo.error import RecordingNotSupportedException
from pytapo.recording.recording import RecordingInterface


@pytest.fixture
def recording_interface():
    perform_request = Mock()
    execute_function = Mock()
    child_id = "123"
    return RecordingInterface(perform_request, execute_function, child_id)


def test_get_recordings_list(recording_interface):
    recording_interface.execute_function.return_value = {
        "playback": {"search_results": ["result1", "result2"]}
    }
    recordings = recording_interface.get_recordings_list("20220101", "20220102")
    assert recordings == ["result1", "result2"]
    recording_interface.execute_function.assert_called_once_with(
        "searchDateWithVideo",
        {
            "playback": {
                "search_year_utility": {
                    "channel": [0],
                    "end_date": "20220102",
                    "start_date": "20220101",
                }
            }
        },
    )


def test_get_recordings_list_not_supported(recording_interface):
    recording_interface.execute_function.return_value = {}
    with pytest.raises(RecordingNotSupportedException):
        recording_interface.get_recordings_list("20220101", "20220102")


def test_get_recordings(recording_interface):
    recording_interface.execute_function.return_value = {
        "playback": {"search_video_results": ["result1", "result2"]}
    }
    # let's say get_user_id() returns "321"
    recording_interface.get_user_id = Mock(return_value="321")
    recordings = recording_interface.get_recordings("20220101")
    assert recordings == ["result1", "result2"]
    recording_interface.execute_function.assert_called_once_with(
        "searchVideoOfDay",
        {
            "playback": {
                "search_video_utility": {
                    "channel": 0,
                    "date": "20220101",
                    "end_index": 999999999,
                    "id": "321",
                    "start_index": 0,
                }
            }
        },
    )


def test_get_recordings_not_supported(recording_interface):
    recording_interface.execute_function.return_value = {}
    recording_interface.get_user_id = Mock(return_value="321")
    with pytest.raises(RecordingNotSupportedException):
        recording_interface.get_recordings("20220101")
