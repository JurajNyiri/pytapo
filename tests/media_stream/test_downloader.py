import pytest
import asyncio
from unittest.mock import patch, MagicMock
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


@pytest.fixture
def downloader():
    tapo = Tapo("192.168.0.10", "admin", "admin")
    return Downloader(tapo, 1624627523, 1624628123, "./", 5, False, 200, "output.mp4")


def test_md5(mock_open, mock_isfile, downloader):
    mock_isfile.return_value = True
    mock_open.return_value.__enter__.return_value.read.return_value = b"filecontent"
    result = downloader.md5("filename")
    assert result is not False



@pytest.mark.asyncio
async def test_downloadFile(downloader):
    async def async_generator():
        for _ in range(5):
            yield {
                "currentAction": "action",
                "fileName": "fileName",
                "progress": 10,
                "total": 50,
            }

    downloader.download = AsyncMock()
    downloader.download.return_value = async_generator()
    result = await downloader.downloadFile()
    assert result is not None


def test__prepare_payload(downloader):
    payload = downloader._prepare_payload()
    assert "type" in payload
    assert "seq" in payload
    assert "params" in payload


def test__create_status(downloader):
    result = downloader._create_status("Downloading", "video.mp4", 50, 100)
    assert result["currentAction"] == "Downloading"
    assert result["fileName"] == "video.mp4"
    assert result["progress"] == 50
    assert result["total"] == 100
