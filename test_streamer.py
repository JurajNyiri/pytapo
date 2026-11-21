"""Offline tests: Streamer.stop() with audio ends ffmpeg and leaks no file descriptors."""

import asyncio
import os
import stat
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from pytapo.media_stream.downloaderv2 import DownloaderV2
from pytapo.media_stream import downloaderv2
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


# Deadlock regressions adapted from @lusoris in PR #240.
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
        assert downloader.audio_r is None

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


def test_downloaderv2_stalled_audio_write_times_out(monkeypatch):
    monkeypatch.setattr(downloaderv2, "AUDIO_WRITE_TIMEOUT", 0.03)

    async def run():
        downloader = DownloaderV2(MagicMock(), 100, 200, 0)
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        downloader.audio_w = write_fd
        try:
            while True:
                try:
                    os.write(write_fd, b"x" * 4096)
                except BlockingIOError:
                    break
            with pytest.raises(TimeoutError, match="audio pipe"):
                await asyncio.wait_for(downloader._write_audio_frame(b"audio"), 1)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    asyncio.run(run())


def test_downloaderv2_does_not_write_to_a_reused_audio_descriptor(tmp_path):
    async def run():
        downloader = DownloaderV2(MagicMock(), 100, 200, 0)
        read_fd, write_fd = os.pipe()
        os.set_blocking(write_fd, False)
        downloader.audio_w = write_fd
        owned_fds = [read_fd, write_fd]
        writing = None
        unrelated_file = tmp_path / "unrelated"
        try:
            while True:
                try:
                    os.write(write_fd, b"x" * 4096)
                except BlockingIOError:
                    break
            writing = asyncio.create_task(downloader._write_audio_frame(b"audio"))
            await asyncio.sleep(0.02)
            assert not writing.done()
            os.close(write_fd)
            owned_fds.remove(write_fd)
            downloader.audio_w = None
            replacement = os.open(unrelated_file, os.O_WRONLY | os.O_CREAT, 0o600)
            owned_fds.append(replacement)
            if replacement != write_fd:
                os.dup2(replacement, write_fd)
                owned_fds.append(write_fd)
            assert await asyncio.wait_for(writing, 1) is False
            assert unrelated_file.read_bytes() == b""
        finally:
            if writing is not None:
                writing.cancel()
                await asyncio.gather(writing, return_exceptions=True)
            for fd in owned_fds:
                os.close(fd)

    asyncio.run(run())


def test_downloaderv2_cut_clears_closed_audio_writer():
    async def run():
        downloader = DownloaderV2(
            MagicMock(), 100, 110, 0, padding=0, includeAudio=True
        )
        downloader.streamProcess = MagicMock()
        downloader.streamProcess.stdin.is_closing.return_value = False
        read_fd, write_fd = os.pipe()
        downloader.audio_w = write_fd
        stderr = asyncio.StreamReader()
        stderr.feed_data(b"frame=1 time=00:00:15.00\n")
        stderr.feed_eof()
        try:
            await downloader._print_ffmpeg_logs(stderr)
            assert downloader.audio_w is None
            with pytest.raises(OSError):
                os.fstat(write_fd)
            with patch("pytapo.media_stream.downloaderv2.os.write") as write:
                assert await downloader._write_audio_frame(b"late audio") is False
                write.assert_not_called()
        finally:
            os.close(read_fd)
            if downloader.audio_w is not None:
                os.close(downloader.audio_w)

    asyncio.run(run())
