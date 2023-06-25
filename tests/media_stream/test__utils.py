import pytest
from pytapo.media_stream._utils import (
    md5digest,
    generate_nonce,
    parse_http_headers,
    parse_http_response,
    parse_time,
    index_from,
    annexB2AVC,
)


def test_md5digest():
    assert md5digest(b"hello") == b"5D41402ABC4B2A76B9719D911017C592"


def test_generate_nonce():
    nonce = generate_nonce(10)
    assert len(nonce) == 20  # Hex encoding doubles the size


def test_parse_http_headers():
    headers = b"Content-Type: text/html\r\nContent-Length: 100"
    expected = {"Content-Type": "text/html", "Content-Length": "100"}
    assert parse_http_headers(headers) == expected


def test_parse_http_response():
    response = b"HTTP/1.1 200 OK"
    assert parse_http_response(response) == (b"HTTP/1.1", 200, b"OK")


def test_parse_time():
    assert parse_time(b"\x01\x01\x01\x01\x01") == 4194432


def test_index_from():
    assert index_from(b"hello", b"l", 2) == 2


def test_annexB2AVC():
    data = b"\x00\x00\x00\x01\x01\x01\x01\x01\x00\x00\x00\x01\x01\x01\x01\x01"
    expected = b"\x00\x00\x00\x04\x01\x01\x01\x01\x00\x00\x00\x04\x01\x01\x01\x01"
    assert annexB2AVC(data) == expected
