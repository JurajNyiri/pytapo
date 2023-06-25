import pytest
from rtp import PayloadType
from pytapo.media_stream.pes import PES, StreamType


def test_pes_initialization():
    pes = PES()
    assert pes.StreamType is None
    assert pes.StreamID is None
    assert pes.Payload is None
    assert pes.Mode is None
    assert pes.Size is None
    assert pes.Sequence == 0
    assert pes.Timestamp == 0


def test_set_buffer():
    pes = PES()
    pes.SetBuffer(10, b"\x00\x00\x10")

    assert pes.Mode == pes.ModeSize
    assert pes.Size == 10
    assert pes.Payload == b"\x00\x00\x10"


def test_append_buffer():
    pes = PES()
    pes.AppendBuffer(b"\x01\x02\x03")

    assert pes.Payload == b"\x01\x02\x03"

    pes.AppendBuffer(b"\x04\x05")
    assert pes.Payload == b"\x01\x02\x03\x04\x05"


def test_get_packet_for_pcmatapo():
    pes = PES()
    pes.StreamType = StreamType.PCMATapo
    pes.SetBuffer(3, b"\x00\x00\x00abc")
    packet = pes.GetPacket()

    assert packet.payloadType == PayloadType.PCMA
    assert packet.payload == b"abc"
    assert packet.timestamp == 3
    assert packet.sequenceNumber == 1
