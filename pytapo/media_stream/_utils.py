import hashlib
import os
from enum import Enum

from ..const import EncryptionMethod

from typing import Mapping, Tuple, Optional


class StreamType(Enum):
    Stream = "Stream"
    Download = "Download"


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
