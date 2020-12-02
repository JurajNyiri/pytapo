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
    return http_ver, int(status_code.decode()), status
