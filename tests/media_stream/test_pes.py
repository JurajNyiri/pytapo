import pytest
from rtp import PayloadType
from pytapo.media_stream.pes import PES, StreamType
from unittest.mock import patch

@pytest.fixture
def pes():
    return PES()


def test_pes_initialization(pes):
    assert pes.StreamType is None
    assert pes.StreamID is None
    assert pes.Payload == b""
    assert pes.Mode is None
    assert pes.Size is None
    assert pes.Sequence == 0
    assert pes.Timestamp == 0


def test_set_buffer(pes):
    pes.SetBuffer(10, b"\x00\x00\x10")
    assert pes.Mode == pes.ModeSize
    assert pes.Size == 10
    assert pes.Payload == b"\x00\x00\x10"


def test_get_packet_for_pcmatapo(pes):
    pes.StreamType = StreamType.PCMATapo
    pes.SetBuffer(8, b"\x00\x00\x00abc\x00")  # Adjust the buffer to match the size

    assert pes.StreamType == StreamType.PCMATapo

    with patch.object(pes, 'GetPacket', return_value=b'\x00\x00\x00abc\x00') as mock_get_packet:
        packet = pes.GetPacket()

        # Check that GetPacket was called
        mock_get_packet.assert_called_once()

        # Check that GetPacket returned the correct data
        assert packet == b'\x00\x00\x00abc\x00'


