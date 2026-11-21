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
ffprobe = os.path.basename(sys.argv[0]) == "ffprobe"
if not ffprobe and os.environ.get("FAKE_WRITE_FIRST"):
    open(sys.argv[-1], "wb").close()
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
if ffprobe:
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


@pytest.mark.parametrize("cancels", [1, 2])
def test_save_cancelled_removes_incomplete_output(fake_ffmpeg, monkeypatch, cancels):
    """An incomplete file would be skipped as already downloaded next time."""
    monkeypatch.setenv("FAKE_SLEEP", "30")
    monkeypatch.setenv("FAKE_WRITE_FIRST", "1")
    pidfile = fake_ffmpeg / "pid"
    out = fake_ffmpeg / "out.mp4"

    async def run():
        task = asyncio.ensure_future(_converter().save(str(out), 10))
        while not pidfile.exists() or not pidfile.read_text() or not out.exists():
            await asyncio.sleep(0.02)
        for _ in range(cancels):
            task.cancel()
            await asyncio.sleep(0)
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert not out.exists()
    assert _no_temp_dirs(fake_ffmpeg)


def _slow_in_thread(monkeypatch, owner, name):
    """Make owner.name block its thread for a while; returns an event set when it starts."""
    import threading

    started = threading.Event()
    original = getattr(owner, name)

    def slow(*args, **kwargs):
        started.set()
        time.sleep(0.3)
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, slow)
    return started


async def _cancel_when(started, coro, cancels):
    task = asyncio.ensure_future(coro)
    while not started.is_set():
        await asyncio.sleep(0.01)
    for _ in range(cancels):
        task.cancel()
        await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.parametrize("cancels", [1, 2])
def test_save_cancelled_while_creating_temp_dir(fake_ffmpeg, monkeypatch, cancels):
    """The directory created after the cancellation is removed as well."""
    import tempfile

    started = _slow_in_thread(monkeypatch, tempfile, "mkdtemp")
    out = fake_ffmpeg / "out.mp4"
    asyncio.run(_cancel_when(started, _converter().save(str(out), 10), cancels))
    assert _no_temp_dirs(fake_ffmpeg)
    assert not (fake_ffmpeg / "pid").exists()  # ffmpeg not started
    assert not out.exists()


@pytest.mark.parametrize("cancels", [1, 2])
def test_length_async_cancelled_while_writing_temp_file(fake_ffmpeg, monkeypatch, cancels):
    """The file written after the cancellation is removed, ffprobe is not started."""
    import tempfile

    import pytapo.media_stream.convert as convert

    tmpdir = fake_ffmpeg / "tmp"
    tmpdir.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmpdir))
    started = _slow_in_thread(monkeypatch, convert, "_write_temporary_file")
    asyncio.run(_cancel_when(started, _converter().getLengthAsync(exact=True), cancels))
    assert list(tmpdir.iterdir()) == []
    assert not (fake_ffmpeg / "pid").exists()


def test_write_temporary_file_removed_on_error(tmp_path, monkeypatch):
    import tempfile

    from pytapo.media_stream.convert import _write_temporary_file

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(TypeError):
        _write_temporary_file("not bytes")
    assert list(tmp_path.iterdir()) == []


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


def test_file_io_limits_threads_and_frees_slots_only_when_done():
    """Calls hanging on an unreachable share occupy at most FILE_IO_THREADS threads."""
    import threading

    from pytapo.media_stream._utils import FILE_IO_THREADS, run_file_io

    release = threading.Event()
    started = []

    def hanging(n):
        started.append(n)
        release.wait(5)
        return n

    async def run():
        tasks = [asyncio.ensure_future(run_file_io(hanging, n)) for n in range(FILE_IO_THREADS + 1)]
        _, gap = await _max_loop_gap(asyncio.sleep(0.3))
        assert gap < 0.2  # the event loop keeps running
        assert len(started) == FILE_IO_THREADS
        # Cancelling (twice) returns at once, but does not free the slots
        for t in tasks[:FILE_IO_THREADS]:
            t.cancel()
            await asyncio.sleep(0)
            t.cancel()
        await asyncio.sleep(0.2)
        assert all(t.cancelled() for t in tasks[:FILE_IO_THREADS])
        assert len(started) == FILE_IO_THREADS
        release.set()  # the hanging calls return: the waiting call runs
        assert await tasks[-1] == FILE_IO_THREADS

    asyncio.run(run())


def test_file_io_passes_errors_and_survives_a_closed_loop():
    import threading

    from pytapo.media_stream._utils import run_file_io

    def broken():
        raise OSError("share unreachable")

    async def raises():
        with pytest.raises(OSError):
            await run_file_io(broken)

    asyncio.run(raises())

    release = threading.Event()
    errors = []
    old_hook = threading.excepthook
    threading.excepthook = lambda args: errors.append(args.exc_value)
    try:

        async def leave_running():
            task = asyncio.ensure_future(run_file_io(release.wait, 5))
            await asyncio.sleep(0.05)
            task.cancel()

        asyncio.run(leave_running())  # the loop is closed, the thread still runs
        release.set()
        time.sleep(0.2)
    finally:
        threading.excepthook = old_hook
    assert errors == []


def test_file_io_cancel_while_queued_ends_at_once():
    """A call still waiting for a slot can be cancelled at once, also where
    Convert waits for a started call to finish."""
    import threading

    from pytapo.media_stream._utils import FILE_IO_THREADS, run_file_io
    from pytapo.media_stream.convert import _cleanup, _to_thread_to_end

    release = threading.Event()
    ran = []

    def hanging():
        release.wait(5)

    async def run():
        hung = [asyncio.ensure_future(run_file_io(hanging)) for _ in range(FILE_IO_THREADS)]
        await asyncio.sleep(0.05)
        queued = asyncio.ensure_future(_to_thread_to_end(ran.append, "created"))
        cleanup = asyncio.ensure_future(_cleanup(ran.append, "cleaned"))
        await asyncio.sleep(0.05)
        for task in (queued, cleanup):
            task.cancel()
        done, _ = await asyncio.wait((queued, cleanup), timeout=0.5)
        assert done == {queued, cleanup}
        assert queued.cancelled() and cleanup.cancelled()
        assert ran == []  # nothing has started
        release.set()
        await asyncio.gather(*hung)
        for _ in range(50):  # the cleanup still runs once a slot is free
            if ran:
                break
            await asyncio.sleep(0.02)
        assert ran == ["cleaned"]

    asyncio.run(run())


def test_file_io_limit_does_not_keep_the_loop_alive():
    import gc
    import threading
    import weakref

    from pytapo.media_stream._utils import FILE_IO_THREADS, run_file_io

    release = threading.Event()

    async def contend():
        tasks = [
            asyncio.ensure_future(run_file_io(release.wait, 5))
            for _ in range(FILE_IO_THREADS + 2)
        ]
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.gather(*tasks)

    loop = asyncio.new_event_loop()
    loop.run_until_complete(contend())
    loop.close()
    ref = weakref.ref(loop)
    del loop
    gc.collect()
    assert ref() is None
