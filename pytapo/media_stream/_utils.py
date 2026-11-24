import asyncio
import collections
import hashlib
import os
import threading
import weakref
from enum import Enum
from pathlib import Path, PureWindowsPath

from ..const import EncryptionMethod

from typing import Mapping, Tuple, Optional


# File system calls of the media code run in their own daemon threads, at most
# FILE_IO_THREADS at a time per event loop. A call on an unreachable network
# share (e.g. an NFS hard mount) can hang forever; this way it occupies one of
# these slots instead of a thread of the application's executor, and daemon
# threads do not keep the interpreter from exiting.
FILE_IO_THREADS = 2
_LIMIT_ATTRIBUTE = "_pytapo_file_io_limit"
_file_io_limits = weakref.WeakKeyDictionary()  # loops without attribute support


class _FileIOLimit:
    """Slots for file system threads of one event loop.

    Unlike asyncio.Semaphore it keeps no reference to the loop while idle:
    waiters are futures that are dropped once they are done.
    """

    def __init__(self, slots):
        self._free = slots
        self._waiters = collections.deque()

    async def acquire(self):
        if self._free > 0 and not self._waiters:
            self._free -= 1
            return
        waiter = asyncio.get_running_loop().create_future()
        self._waiters.append(waiter)
        try:
            await waiter
        except asyncio.CancelledError:
            if waiter.done() and not waiter.cancelled():
                # the slot was granted just before the cancellation
                self.release()
            elif waiter in self._waiters:
                # release() may already have dropped the cancelled waiter
                self._waiters.remove(waiter)
            raise

    def release(self):
        while self._waiters:
            waiter = self._waiters.popleft()
            if not waiter.done():
                waiter.set_result(None)  # the slot passes on directly
                return
        self._free += 1


def _file_io_limit(loop):
    limit = getattr(loop, _LIMIT_ATTRIBUTE, None) or _file_io_limits.get(loop)
    if limit is None:
        limit = _FileIOLimit(FILE_IO_THREADS)
        try:
            setattr(loop, _LIMIT_ATTRIBUTE, limit)
        except AttributeError:
            _file_io_limits[loop] = limit
    return limit


async def start_file_io(func, *args, **kwargs):
    """Wait for a free slot, start a blocking file system call in it and
    return a future for its result.

    Cancelling while waiting for the slot ends at once, nothing has started
    then. The slot is only freed when the call has really returned.
    """
    loop = asyncio.get_running_loop()
    limit = _file_io_limit(loop)
    await limit.acquire()
    future = loop.create_future()

    def finish(result, error):
        if not future.done():
            if error is None:
                future.set_result(result)
            else:
                future.set_exception(error)
        limit.release()

    def worker():
        try:
            outcome = (func(*args, **kwargs), None)
        except BaseException as error:  # handed to the awaiting task
            outcome = (None, error)
        try:
            loop.call_soon_threadsafe(finish, *outcome)
        except RuntimeError:
            pass  # the event loop has been closed meanwhile

    try:
        threading.Thread(target=worker, name="pytapo-file-io", daemon=True).start()
    except BaseException:
        limit.release()
        raise
    return future


async def run_file_io(func, *args, **kwargs):
    """Run a blocking file system call without blocking the event loop.

    Cancelling returns at once, also while the call is running.
    """
    return await (await start_file_io(func, *args, **kwargs))


class StreamType(Enum):
    Stream = "Stream"
    Download = "Download"


def media_output_path(output_directory, file_name):
    """Keep a caller-provided filename inside the selected output directory."""
    if (
        not isinstance(file_name, str)
        or not file_name
        or file_name in (".", "..")
        or any(character in file_name for character in ("/", "\\", "\x00"))
        or PureWindowsPath(file_name).drive
    ):
        raise ValueError("fileName must be a single filename")
    directory = Path(output_directory).resolve()
    path = Path(os.path.abspath(os.path.join(output_directory, file_name)))
    if not path.resolve().is_relative_to(directory):
        raise ValueError("fileName escapes outputDirectory")
    return str(path)


def pwd_digest(
    to_hash: bytes,
    encryptionMethod: EncryptionMethod,
) -> bytes:
    if encryptionMethod == EncryptionMethod.MD5:
        return hashlib.md5(to_hash).digest().hex().upper().encode()
    elif encryptionMethod == EncryptionMethod.SHA256:
        return hashlib.sha256(to_hash).digest().hex().upper().encode()
    else:
        raise Exception(
            f"Failure generating digest password, incorrect hashing method: {encryptionMethod}"
        )


def generate_nonce(length: int) -> bytes:
    return os.urandom(length).hex().encode()


def parse_http_headers(data: bytes) -> Mapping[str, str]:
    return {
        i[0].strip(): i[1].strip()
        for i in (j.split(":", 1) for j in data.decode().strip().split("\r\n"))
    }


# Some devices respond with 'HTTP ERROR 401HTTP/1.0 200 OK'. This fixes it. ¯\_(ツ)_/¯
def check_and_correct_http_response(data: bytes) -> bytes:
    __HTTP_VERSION_LIST = [
        "HTTP/0.9",
        "HTTP/1.0",
        "HTTP/1.1",
        "HTTP/2",
        "HTTP/3",
    ]
    decode_data = data.decode()
    check = any([decode_data.startswith(v) for v in __HTTP_VERSION_LIST])
    if not check:
        for v in __HTTP_VERSION_LIST:
            pos = decode_data.find(v)
            if pos != -1:
                return decode_data[pos:].encode()
    else:
        return data


def parse_http_response(res_line: bytes) -> Tuple[bytes, int, Optional[bytes]]:
    res_line = check_and_correct_http_response(res_line)
    http_ver, status_code_and_status = res_line.split(b" ", 1)
    if b" " in status_code_and_status:
        status_code, status = status_code_and_status.split(b" ", 1)
    else:
        status_code = status_code_and_status
        status = None
    return http_ver, int(status_code.decode()), status


def parse_time(b: bytes) -> int:
    return (
        ((b[0] & 0x0E) << 29)
        | (b[1] << 22)
        | ((b[2] & 0xFE) << 14)
        | (b[3] << 7)
        | (b[4] >> 1)
    )


def index_from(b: bytes, sep: bytes, start_index: int) -> int:
    if start_index > 0:
        if start_index < len(b):
            if i := b.find(sep, start_index) != -1:
                return i
        return -1
    return b.find(sep)


# todo: is this function correct???
def annexB2AVC(b):
    b = bytes(b)
    i = 0
    # f = open("data1.txt", "w")
    # f.write(str(list(b)))
    # f.close()
    while i < len(b):
        if i + 4 >= len(b):
            break

        size = b[i + 4 :].find(b"\x00\x00\x00\x01")

        # f = open("data1.5.txt", "w")
        # f.write(str(list(b[i + 4 :])))
        # f.close()

        if size < 0:
            size = len(b) - (i + 4)

        size_bytes = size.to_bytes(4, "big")

        b = bytearray(b)
        b[i : i + 4] = size_bytes
        b = bytes(b)

        i += size + 4
    # f = open("data2.txt", "w")
    # f.write(str(list(b)))
    # f.close()
    # sys.exit(0)

    return bytearray(b)
