import hashlib
import os
from typing import Mapping, Tuple, Optional


def md5digest(to_hash: bytes) -> bytes:
    return hashlib.md5(to_hash).digest().hex().upper().encode()


def generate_nonce(length: int) -> bytes:
    return os.urandom(length).hex().encode()


def parse_http_headers(data: bytes) -> Mapping[str, str]:
    return {
        i[0].strip(): i[1].strip()
        for i in (j.split(":", 1) for j in data.decode().strip().split("\r\n"))
    }


def parse_http_response(res_line: bytes) -> Tuple[bytes, int, Optional[bytes]]:
    http_ver, status_code_and_status = res_line.split(b" ", 1)
    if b" " in status_code_and_status:
        status_code, status = status_code_and_status.split(b" ", 1)
    else:
        status_code = status_code_and_status
        status = None
    try:
        status_code = int(status_code.decode())
    except ValueError:
        status_code = 0  # or any default value
    return http_ver, status_code, status


def parse_time(b: bytes) -> int:
    return (
        ((b[0] & 0x0E) << 29)
        | (b[1] << 22)
        | ((b[2] & 0xFE) << 14)
        | (b[3] << 7)
        | (b[4] >> 1)
    )


def index_from(b: bytes, sep: bytes, start_index: int) -> int:
    return b.find(sep, start_index) if start_index >= 0 and start_index < len(b) else -1


def annexB2AVC(b: bytes):
    b = bytearray(b)
    i = 0
    while i < len(b):
        if i + 4 >= len(b):
            break

        size = b[i + 4 :].find(b"\x00\x00\x00\x01")
        if size < 0:
            size = len(b) - (i + 4)

        size_bytes = size.to_bytes(4, "big")
        b[i : i + 4] = size_bytes
        i += size + 4

    return b
