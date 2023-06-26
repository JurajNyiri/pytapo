import pytest
import asyncio
from unittest.mock import patch, MagicMock
from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader

# Define a maximum wait time for all async tests
ASYNC_TEST_TIMEOUT = 5  # Adjust this value as needed


class MockDownloader:
    async def download(self):
        data = [
            {
                "currentAction": "action",
                "fileName": "fileName",
                "progress": 10,
                "total": 50,
            }
            for _ in range(5)
        ]
        for d in data:
            yield d


class AsyncMock(MagicMock):
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)


class AsyncIterable:
    def __init__(self, data):
        self.data = data

    async def __aiter__(self):  # Make this an async function
        return self

    async def __anext__(self):
        if not self.data:
            raise StopAsyncIteration
        return self.data.pop(0)


@pytest.fixture
def downloader():
    tapo = Tapo("192.168.0.10", "admin", "admin")
    tapo.getUserID = MagicMock(return_value="some_user_id")  # mock getUserID method
    return Downloader(tapo, 1624627523, 1624628123, "./", 5, False, 200, "output.mp4")


@pytest.fixture
def mock_open(mocker):
    return mocker.patch("builtins.open", new_callable=MagicMock)


@pytest.fixture
def mock_isfile(mocker):
    return mocker.patch("os.path.isfile", return_value=True)


@pytest.mark.asyncio
async def test_downloadFile(mocker, downloader):
    downloader.download = MockDownloader().download
    result = await asyncio.wait_for(
        downloader.downloadFile(), timeout=ASYNC_TEST_TIMEOUT
    )
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
