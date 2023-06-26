import pytest
from unittest.mock import MagicMock, Mock
from pytapo.settings.device import DeviceInterface


class TestDeviceInterface:
    @pytest.fixture
    def mock_request(self):
        mock = Mock()
        mock.return_value = {"success": True}
        return mock

    @pytest.fixture
    def mock_execute(self):
        mock = Mock()
        mock.return_value = {"success": True}
        return mock

    @pytest.fixture
    def device_interface(self, mock_execute, mock_request):
        device_interface = DeviceInterface(mock_request, mock_execute, None)
        device_interface.execute_function = mock_execute
        device_interface.perform_request = mock_request
        return device_interface

    def test_set_privacy_mode(self, device_interface, mock_execute):
        mock_execute.return_value = {"success": True}
        result = device_interface.setPrivacyMode(True)
        assert result == {"success": True}

    def test_get_privacy_mode(self, device_interface, mock_execute, mock_request):
        mock_request.return_value = {"lens_mask": {"lens_mask_info": {"enabled": "on"}}}
        mock_execute.return_value = {"lens_mask": {"lens_mask_info": {"enabled": "on"}}}
        result = device_interface.getPrivacyMode()
        assert result == {"enabled": "on"}

    def test_set_media_encrypt(self, device_interface, mock_execute, mock_request):
        mock_execute.return_value = {"success": True}
        assert device_interface.setMediaEncrypt(True) == {"success": True}

    def test_get_media_encrypt(self, device_interface, mock_execute):
        mock_execute.return_value = {"cet": {"media_encrypt": {"enabled": "on"}}}
        result = device_interface.getMediaEncrypt()
        assert result == {"enabled": "on"}

    def test_set_auto_track_target(self, device_interface, mock_execute):
        mock_execute.return_value = {"success": True}
        assert device_interface.setAutoTrackTarget(True) == {"success": True}

    def test_get_audio_spec(self, device_interface, mock_execute, mock_request):
        mock_execute.return_value = {"audio_capability": {"device_speaker": "on"}}
        mock_request.return_value = {"audio_capability": {"device_speaker": "on"}}
        result = device_interface.getAudioSpec()
        assert result == {"audio_capability": {"device_speaker": "on"}}

    def test_get_vhttpd(self, device_interface, mock_execute, mock_request):
        mock_request.return_value = {"cet": {"vhttpd": "on"}}
        result = device_interface.getVhttpd()
        assert result == {"cet": {"vhttpd": "on"}}

    def test_get_model(self, device_interface, mock_execute):
        mock_execute.return_value = "test_model"
        result = device_interface.getModel()
        assert result == "test_model"

    def test_get_time(self, device_interface, mock_execute):
        mock_execute.return_value = "12:00"
        result = device_interface.getTime()
        assert result == "12:00"

    def test_get_osd(self, device_interface, mock_execute):
        mock_execute.return_value = {"date": {"enabled": "on"}}
        result = device_interface.getOsd()
        assert result == {"date": {"enabled": "on"}}

    def test_get_events(self, device_interface, mock_execute):
        timeCorrection = 10
        device_interface.getTimeCorrection = MagicMock(return_value=timeCorrection)
        mock_execute.return_value = {
            "playback": {
                "search_detection_list": [{"event": "event_1", "start_time": "10:00"}]
            }
        }
        result = device_interface.getEvents()
        hours, minutes = map(int, "10:00".split(":"))
        expected_start_time = "{:02d}:{}".format(hours + timeCorrection, minutes)
        assert result == [{"event": "event_1", "start_time": expected_start_time}]

