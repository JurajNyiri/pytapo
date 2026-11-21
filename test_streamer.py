"""Offline tests: Streamer.stop() with audio ends ffmpeg and leaks no file descriptors."""

import asyncio
import os
import stat
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

from pytapo.media_stream.downloaderv2 import DownloaderV2
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


AUDIO_TOTAL_BYTES = 200000

# Writes >300 KB of stderr logs before opening and draining the audio pipe.
FAKE_CHATTERING_FFMPEG = """#!{python}
import os, sys
audio = next(a for a in sys.argv if a.startswith("/dev/fd/"))
line = ("x" * 100 + "\\n").encode()
for _ in range(4000):
    os.write(2, line)
fd = os.open(audio, os.O_RDONLY)
total = 0
while True:
    chunk = os.read(fd, 4096)
    if not chunk:
        break
    total += len(chunk)
os.close(fd)
open(os.environ["FAKE_AUDIO_BYTES"], "w").write(str(total))
"""


@pytest.fixture
def fake_chattering_ffmpeg(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    exe = bindir / "ffmpeg"
    exe.write_text(FAKE_CHATTERING_FFMPEG.format(python=sys.executable))
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_AUDIO_BYTES", str(tmp_path / "audio_bytes"))
    return tmp_path


class AudioBurstSession:
    """Media session yielding enough audioPayload to overfill a 64 KiB pipe."""

    def set_window_size(self, size):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def transceive(self, *args, **kwargs):
        chunk = MagicMock(
            mimetype="video/mp2t",
            audioPayload=b"a" * 20000,
            plaintext=b"",
        )
        for _ in range(AUDIO_TOTAL_BYTES // 20000):
            yield chunk


async def _run_with_watchdog(proc, stream_task, on_stream_done=None):
    last_beat = time.monotonic()
    max_gap = 0.0
    done = threading.Event()

    async def heartbeat():
        nonlocal last_beat, max_gap
        while not done.is_set():
            await asyncio.sleep(0.05)
            now = time.monotonic()
            gap = now - last_beat
            if gap > max_gap:
                max_gap = gap
            last_beat = now

    def watchdog():
        nonlocal max_gap
        while not done.wait(0.05):
            gap = time.monotonic() - last_beat
            if gap > max_gap:
                max_gap = gap
            if gap > 3.0:
                try:
                    proc.kill()
                except OSError:
                    pass
                break

    beat_task = asyncio.create_task(heartbeat())
    watcher = threading.Thread(target=watchdog, daemon=True)
    watcher.start()
    try:
        await stream_task
        if on_stream_done is not None:
            on_stream_done()
        await proc.wait()
    finally:
        done.set()
        watcher.join(timeout=2.0)
        beat_task.cancel()
        try:
            await beat_task
        except asyncio.CancelledError:
            pass
    return max_gap


def test_streamer_audio_pipe_does_not_deadlock_event_loop(
    fake_chattering_ffmpeg,
):
    async def run():
        tapo = MagicMock()
        tapo.getMediaSession.return_value = AudioBurstSession()
        tapo.getAudioConfig.return_value = {}
        streamer = Streamer(tapo, includeAudio=True)
        info = await streamer.start()
        try:
            return await _run_with_watchdog(
                info["ffmpegProcess"], info["streamProcess"]
            )
        finally:
            await streamer.stop()

    max_gap = asyncio.run(run())
    audio_bytes_file = fake_chattering_ffmpeg / "audio_bytes"
    assert max_gap < 3.0
    assert int(audio_bytes_file.read_text()) == AUDIO_TOTAL_BYTES


def test_downloaderv2_audio_pipe_does_not_deadlock_event_loop(
    fake_chattering_ffmpeg,
):
    async def run():
        tapo = MagicMock()
        tapo.getMediaSession.return_value = AudioBurstSession()
        tapo.getAudioConfig.return_value = {}
        tapo.getUserID.return_value = 1
        downloader = DownloaderV2(
            tapo,
            startTime=100,
            endTime=200,
            timeCorrection=0,
            includeAudio=True,
        )
        info = await downloader.start()
        if downloader.audio_r is not None:
            os.close(downloader.audio_r)
            downloader.audio_r = None

        def close_audio_w():
            if downloader.audio_w is not None:
                os.close(downloader.audio_w)
                downloader.audio_w = None

        try:
            return await _run_with_watchdog(
                info["ffmpegProcess"],
                info["streamProcess"],
                on_stream_done=close_audio_w,
            )
        finally:
            close_audio_w()
            await downloader.stop()

    max_gap = asyncio.run(run())
    audio_bytes_file = fake_chattering_ffmpeg / "audio_bytes"
    assert max_gap < 3.0
    assert int(audio_bytes_file.read_text()) == AUDIO_TOTAL_BYTES
