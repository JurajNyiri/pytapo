"""Offline tests for recordings stored on a Tapo hub's SD card, no camera needed."""

import asyncio
from datetime import datetime
from types import SimpleNamespace

import mock
import pytest

from pytapo import Tapo
from pytapo.logger import Logger
from pytapo.media_stream._utils import StreamType
from pytapo.media_stream.snapshot import getRecordingSnapshot

DAYS = {"2026": ["20261001", "20261101"], "2025": ["20250829"], "2023": ["20230101"]}


def hubCamera(childID="8021AB", components=("playback", "recordDownload")):
    tapo = Tapo.__new__(Tapo)
    tapo.host = "192.0.2.1"
    tapo.cloudPassword = "cloud"
    tapo.superSecretKey = ""
    tapo.streamPort = 8800
    tapo.playerID = "player"
    tapo.childID = childID
    tapo.userID = False
    tapo.hubRecordDownload = None
    tapo.logger = Logger(False, False)
    tapo.basicInfo = {"device_info": {"basic_info": {"mac": "AA-BB-CC-00-11-22"}}}
    tapo.getEncryptionMethod = mock.Mock(return_value=None)
    tapo.searches = []

    def executeFunction(method, params, retry=False):
        if method == "getAppComponentList":
            componentList = [{"name": name} for name in components]
            return {"app_component": {"app_component_list": componentList}}
        if method == "getUserID":
            return {"user_id": 1}
        if method == "searchVideoWithUTC":
            return {"playback": {"search_video_results": []}}
        search = params["playback"]["search_year_utility"]
        start, end = search["start_date"], search["end_date"]
        tapo.searches.append((start, end))
        days = [day for day in DAYS.get(start[:4], []) if start <= day <= end]
        return {
            "playback": {
                "search_results": [
                    {f"search_results_{i}": {"date": day}}
                    for i, day in enumerate(days, start=1)
                ]
            }
        }

    tapo.executeFunction = executeFunction
    return tapo


def dates(results):
    return [result[key]["date"] for result in results for key in result]


def test_hub_camera_searches_one_year_at_a_time():
    tapo = hubCamera()
    results = tapo.getRecordingsList(end_date="20261101")
    assert tapo.searches == [
        ("20260101", "20261101"),
        ("20250101", "20251231"),
        ("20240101", "20241231"),
    ]
    assert dates(results) == ["20250829", "20261001", "20261101"]
    assert tapo.hubRecordDownload is True


def test_hub_camera_search_stops_at_start_date():
    tapo = hubCamera()
    tapo.getRecordingsList(start_date="20250315", end_date="20261101")
    assert tapo.searches == [("20260101", "20261101"), ("20250315", "20251231")]


def test_camera_without_hub_searches_once():
    tapo = hubCamera(childID=None)
    tapo.getRecordingsList()
    assert tapo.searches == [("20000101", datetime.today().strftime("%Y%m%d"))]


def test_search_without_playback():
    tapo = hubCamera()
    tapo.executeFunction = mock.Mock(return_value={})
    with pytest.raises(Exception, match="Video playback is not supported"):
        tapo.getRecordingsList(end_date="20261101")
    assert tapo.hubRecordDownload is None


def test_getRecordings_caches_record_download():
    tapo = hubCamera()
    assert tapo.getRecordings("20261101") == []
    assert tapo.hubRecordDownload is True


def test_record_download_needs_the_component():
    tapo = hubCamera(components=("playback",))
    assert tapo.isHubRecordDownload() is False
    assert tapo.hubRecordDownload is False


def test_media_session_for_hub_recordings():
    tapo = hubCamera()
    tapo.hubRecordDownload = True
    for mediaType in (0, 2):
        session = tapo.getMediaSession(StreamType.Download, media_type=mediaType)
        assert session.query_params == {
            "camera_mac": "AABBCC001122",
            "type": "download",
            "playerId": "player",
            "media_type": mediaType,
        }


def test_media_session_stays_sdvod():
    for cached, mediaType in ((None, 0), (False, 0), (True, 3)):
        tapo = hubCamera()
        tapo.hubRecordDownload = cached
        session = tapo.getMediaSession(StreamType.Download, media_type=mediaType)
        assert session.query_params["type"] == "sdvod"


def test_child_mac_after_getMost():
    tapo = hubCamera()
    tapo.basicInfo = [tapo.basicInfo]
    assert tapo.getChildMAC() == "AABBCC001122"
    tapo.basicInfo = [False]
    assert tapo.getChildMAC() == ""


class FakeMediaSession:
    def set_window_size(self, window_size):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def transceive(self, data, no_data_timeout=None):
        yield SimpleNamespace(mimetype="image/jpeg", plaintext=b"jpeg")


def test_recording_snapshot_opens_a_thumbnail_session():
    tapo = hubCamera()
    tapo.userID = 1
    tapo.getMediaSession = mock.Mock(return_value=FakeMediaSession())
    assert asyncio.run(getRecordingSnapshot(tapo, 1793534230)) == b"jpeg"
    tapo.getMediaSession.assert_called_once_with(StreamType.Download, media_type=2)
