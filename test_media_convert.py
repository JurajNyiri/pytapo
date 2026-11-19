"""Offline tests: media conversion must not block the event loop and must clean up on cancellation.

ffmpeg/ffprobe are replaced by small fake executables on PATH.
"""

import asyncio
import os
import stat
import sys
import time

import pytest

from pytapo.media_stream.convert import Convert
from pytapo.media_stream.downloader import Downloader

FAKE = """#!{python}
import os, sys, time
pidfile = os.environ.get("FAKE_PIDFILE")
if pidfile:
    with open(pidfile, "w") as f:
        f.write(str(os.getpid()))
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
if os.path.basename(sys.argv[0]) == "ffprobe":
    print(os.environ.get("FAKE_LENGTH", "12.5"))
else:
    open(sys.argv[-1], "wb").close()
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


@pytest.fixture
def fake_ffmpeg(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("ffmpeg", "ffprobe"):
        exe = bindir / name
        exe.write_text(FAKE.format(python=sys.executable))
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_PIDFILE", str(tmp_path / "pid"))
    return tmp_path


def _alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _max_loop_gap(coro):
    """Run coro and measure the longest time the event loop could not run a ticker."""
    gaps = []

    async def ticker():
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            gaps.append(now - last)
            last = now

    t = asyncio.ensure_future(ticker())
    try:
        result = await coro
    finally:
        t.cancel()
    return result, max(gaps or [0])


def _converter():
    c = Convert()
    c.write(b"\x47" * 188, b"\x00" * 160)
    return c


def test_md5_in_blocks_and_missing_file(tmp_path):
    import hashlib

    f = tmp_path / "a.mp4"
    f.write_bytes(b"x" * 3_000_000)
    d = Downloader.__new__(Downloader)
    assert asyncio.run(d.md5(str(f))) == hashlib.md5(f.read_bytes()).hexdigest()
    assert asyncio.run(d.md5(str(tmp_path / "missing.mp4"))) is False


def test_md5_stops_after_cancel(tmp_path, monkeypatch):
    """Cancelled (also twice) while hashing: the thread stops after the current block."""
    import hashlib
    import threading
    import time

    f = tmp_path / "big.mp4"
    f.write_bytes(b"x" * (40 * 1024 * 1024))
    blocks = []
    real_md5 = hashlib.md5

    class SlowMd5:
        def __init__(self):
            self._h = real_md5()

        def update(self, data):
            blocks.append(threading.current_thread().name)
            time.sleep(0.05)
            self._h.update(data)

        def hexdigest(self):
            return self._h.hexdigest()

    monkeypatch.setattr(hashlib, "md5", SlowMd5)
    d = Downloader.__new__(Downloader)

    async def run():
        task = asyncio.ensure_future(d.md5(str(f)))
        while not blocks:
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return True
        return False

    assert asyncio.run(run())
    time.sleep(0.3)
    assert len(blocks) <= 3  # of 40
    assert threading.main_thread().name not in blocks


def _no_temp_dirs(path):
    return not [p for p in os.listdir(path) if p.startswith(".pytapo-")]


def test_save_does_not_block_the_event_loop(fake_ffmpeg, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "0.5")
    out = fake_ffmpeg / "out.mp4"
    _, gap = asyncio.run(_max_loop_gap(_converter().save(str(out), 10)))
    assert gap < 0.2
    assert out.exists()
    assert _no_temp_dirs(fake_ffmpeg)


def test_save_raises_when_ffmpeg_fails(fake_ffmpeg, monkeypatch):
    import subprocess

    monkeypatch.setenv("FAKE_EXIT", "1")
    with pytest.raises(subprocess.CalledProcessError):
        asyncio.run(_converter().save(str(fake_ffmpeg / "out.mp4"), 10))
    assert _no_temp_dirs(fake_ffmpeg)


@pytest.mark.parametrize("cancels", [1, 2])
def test_save_cancelled_kills_ffmpeg_and_cleans_up(fake_ffmpeg, monkeypatch, cancels):
    """Unload and the media sync watchdog may both cancel the same task."""
    monkeypatch.setenv("FAKE_SLEEP", "30")
    pidfile = fake_ffmpeg / "pid"

    async def run():
        task = asyncio.ensure_future(_converter().save(str(fake_ffmpeg / "out.mp4"), 10))
        while not pidfile.exists() or not pidfile.read_text():
            await asyncio.sleep(0.02)
        for _ in range(cancels):
            task.cancel()
            await asyncio.sleep(0)
        with pytest.raises(asyncio.CancelledError):
            await task
        return int(pidfile.read_text())

    pid = asyncio.run(run())
    assert not _alive(pid)
    assert _no_temp_dirs(fake_ffmpeg)


def test_length_async_does_not_block_the_event_loop(fake_ffmpeg, monkeypatch):
    monkeypatch.setenv("FAKE_SLEEP", "0.5")
    length, gap = asyncio.run(_max_loop_gap(_converter().getLengthAsync(exact=True)))
    assert length == 12.5
    assert gap < 0.2


@pytest.mark.parametrize("cancels", [1, 2])
def test_length_async_cancelled_kills_ffprobe(fake_ffmpeg, monkeypatch, cancels):
    import tempfile

    monkeypatch.setenv("FAKE_SLEEP", "30")
    pidfile = fake_ffmpeg / "pid"
    tmpdir = fake_ffmpeg / "tmp"
    tmpdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))

    async def run():
        task = asyncio.ensure_future(_converter().getLengthAsync(exact=True))
        while not pidfile.exists() or not pidfile.read_text():
            await asyncio.sleep(0.02)
        for _ in range(cancels):
            task.cancel()
            await asyncio.sleep(0)
        with pytest.raises(asyncio.CancelledError):
            await task
        return int(pidfile.read_text())

    assert not _alive(asyncio.run(run()))
    assert list(tmpdir.iterdir()) == []  # temporary file removed


def test_length_async_ffprobe_fails(fake_ffmpeg, monkeypatch):
    monkeypatch.setenv("FAKE_LENGTH", "N/A")
    assert asyncio.run(_converter().getLengthAsync(exact=True)) is False


def test_length_sync_still_works(fake_ffmpeg, monkeypatch):
    """Backward compatibility: the blocking methods keep returning plain numbers."""
    c = _converter()
    assert c.calculateLength() == 12.5
    assert c.getLength(exact=True) == 12.5
    monkeypatch.setenv("FAKE_LENGTH", "N/A")
    assert _converter().getLength(exact=True) is False


def test_length_sync_and_async_estimate_alike(fake_ffmpeg):
    """Both variants share the estimate between ffprobe runs."""
    sync, asyn = _converter(), _converter()
    sync.getLength()
    asyncio.run(asyn.getLengthAsync())
    for c in (sync, asyn):
        c.write(b"\x47" * 188, b"\x00" * 160)
    # Twice the data at the cached bytes-per-second ratio, without ffprobe.
    assert sync.getLength() == asyncio.run(asyn.getLengthAsync()) == 25.0
