"""Offline tests: Streamer.stop() with audio ends ffmpeg and leaks no file descriptors."""

import asyncio
import os
import stat
import sys
from unittest.mock import MagicMock

import pytest

from pytapo.media_stream.streamer import Streamer

# Like ffmpeg: on SIGTERM it finishes reading its inputs and only exits once the
# audio input has ended.
FAKE_FFMPEG = """#!{python}
import os, signal, sys
audio = next(a for a in sys.argv if a.startswith("/dev/fd/"))
open(os.environ["FAKE_PIDFILE"], "w").write(str(os.getpid()))
signal.signal(signal.SIGTERM, lambda *a: None)
fd = os.open(audio, os.O_RDONLY)
while os.read(fd, 4096):
    pass
"""


@pytest.fixture
def fake_ffmpeg(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "ffmpeg"
    exe.write_text(FAKE_FFMPEG.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_PIDFILE", str(tmp_path / "pid"))
    return tmp_path


class IdleSession:
    """Media session that never sends data, like a camera that has not answered yet."""

    def set_window_size(self, size):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def transceive(self, *args, **kwargs):
        await asyncio.Event().wait()
        yield  # pragma: no cover


def _streamer():
    tapo = MagicMock()
    tapo.getMediaSession.return_value = IdleSession()
    tapo.getAudioConfig.return_value = {}
    return Streamer(tapo, includeAudio=True)


def _open_fds():
    return set(os.listdir("/proc/self/fd"))


def test_stop_with_audio_ends_ffmpeg(fake_ffmpeg):
    async def run():
        before = _open_fds()
        streamer = _streamer()
        info = await streamer.start()
        pidfile = fake_ffmpeg / "pid"
        while not pidfile.exists() or not pidfile.read_text():
            await asyncio.sleep(0.02)
        async with asyncio.timeout(5):
            await streamer.stop()
        return info["ffmpegProcess"].returncode, before, _open_fds()

    returncode, before, after = asyncio.run(run())
    assert returncode is not None  # ffmpeg exited instead of waiting for the audio
    assert after <= before  # no audio pipe end left open


def test_parent_does_not_keep_the_audio_read_end(fake_ffmpeg):
    async def run():
        streamer = _streamer()
        await streamer.start()
        read_end = streamer.audio_r
        async with asyncio.timeout(5):
            await streamer.stop()
        return read_end, streamer.audio_w

    read_end, write_end = asyncio.run(run())
    assert read_end is None
    assert write_end is None
