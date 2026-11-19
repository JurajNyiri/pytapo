"""Offline tests: media conversion must not block the event loop and must clean up on cancellation."""

import asyncio

from pytapo.media_stream.downloader import Downloader


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
