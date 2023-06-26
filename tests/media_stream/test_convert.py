import pytest
from unittest.mock import Mock, mock_open, patch
from subprocess import CompletedProcess
from pytapo.media_stream.convert import Convert


@pytest.fixture
def convert():
    return Convert()


@patch("subprocess.run")
@patch("os.remove")
@patch("builtins.open", new_callable=mock_open)
def test_save(mock_open, mock_remove, mock_run, convert):
    convert.save("fileLocation", 10, "ffmpeg")
    mock_open.assert_called()
    mock_run.assert_called()
    mock_remove.assert_called()


def test_getRefreshIntervalForLengthEstimate(convert):
    convert.addedChunks = 150
    assert convert.getRefreshIntervalForLengthEstimate() == 250


@patch("subprocess.run")
def test_calculateLength(mock_run, convert):
    mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="1.23")
    assert convert.calculateLength() == 1.23


def test_getLength(convert):
    convert.known_lengths = {10: 2.5}
    convert.addedChunks = 20
    assert convert.getLength() == 5


def test_write(convert):
    data = b"video_data"
    audioData = b"audio_data"
    convert.write(data, audioData)
    assert convert.writer.getvalue() == data
    assert convert.audioWriter.getvalue() == audioData
