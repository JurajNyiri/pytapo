import pytest
from unittest.mock import patch
from pytapo.media_stream.tsReader import TSReader


def test_TSReader_init():
    reader = TSReader()
    assert isinstance(reader.b, bytearray)
    assert reader.i == 0
    assert reader.s == TSReader.PacketSize
    assert reader.pmt == 0
    assert reader.pes == {}


@pytest.mark.parametrize(
    "body, expected", [(bytearray(b"test_body"), bytearray(b"test_body"))]
)
def test_TSReader_setBuffer(body, expected):
    reader = TSReader()
    reader.setBuffer(body)
    assert reader.b == expected
    assert reader.i == 0
    assert reader.s == TSReader.PacketSize


def test_TSReader_skip():
    reader = TSReader()
    reader.skip(1)
    assert reader.i == 1


def test_TSReader_read_uint16():
    reader = TSReader()
    reader.setBuffer(bytearray([0x00, 0x01]))
    result = reader.read_uint16()
    assert result == 1
    assert reader.i == 2


def test_TSReader_read_byte():
    reader = TSReader()
    reader.setBuffer(bytearray([0x01]))
    result = reader.read_byte()
    assert result == 0x01
    assert reader.i == 1
