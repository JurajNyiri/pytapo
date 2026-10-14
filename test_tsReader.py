from rtp import PayloadType

from pytapo.media_stream.tsReader import TSReader

PAT_PID = 0x0000


def ts_packet(pid, payload):
    assert len(payload) <= 184
    header = bytes([0x47, 0x40 | (pid >> 8), pid & 0xFF, 0x10])  # PUSI, payload only
    return header + payload + b"\xff" * (184 - len(payload))


def psi_section(table_id, body):
    length = 5 + len(body) + 4  # extension/flags/section numbers + body + CRC32
    header = bytes([table_id, 0xB0 | (length >> 8), length & 0xFF, 0, 1, 0xC1, 0, 0])
    return b"\x00" + header + body + b"\x00" * 4  # pointer field first, dummy CRC32


def pat(programs):
    body = b"".join(
        num.to_bytes(2, "big") + (0xE000 | pmt).to_bytes(2, "big")
        for num, pmt in programs
    )
    return ts_packet(PAT_PID, psi_section(0x00, body))


def pmt(pmt_pid, streams):
    pcr_pid = streams[0][1]
    body = (0xE000 | pcr_pid).to_bytes(2, "big") + b"\xf0\x00"
    body += b"".join(
        bytes([stream_type]) + (0xE000 | pid).to_bytes(2, "big") + b"\xf0\x00"
        for stream_type, pid in streams
    )
    return ts_packet(pmt_pid, psi_section(0x02, body))


def g711_pes(pid, samples):
    # A PES that fills its TS packet exactly: start code, stream id, length, then
    # flags + header length (no PTS) followed by the samples.
    body = b"\x80\x00\x00" + samples
    assert len(body) == 184 - 6
    return ts_packet(pid, b"\x00\x00\x01\xc0" + len(body).to_bytes(2, "big") + body)


def read_all(stream):
    reader = TSReader()
    reader.setBuffer(stream)
    packets = []
    while (pkt := reader.getPacket()) is not None:
        packets.append(pkt)
    return packets


SAMPLES = bytes(range(175))


def test_single_program_audio():
    stream = (
        pat([(1, 0x12)])
        + pmt(0x12, [(0x1B, 0x44), (0x91, 0x45)])
        + g711_pes(0x45, SAMPLES)
    )

    [pkt] = read_all(stream)

    assert pkt.payloadType == PayloadType.PCMU
    assert bytes(pkt.payload) == SAMPLES


def test_audio_in_its_own_program():
    # Layout sent by dual-lens cameras (e.g. C575D): one program per lens and a
    # separate program for the audio, each announced by its own PMT.
    stream = (
        pat([(1, 0x12), (2, 0x13), (3, 0x14)])
        + pmt(0x12, [(0x24, 0x44)])
        + pmt(0x13, [(0x91, 0x54)])
        + pmt(0x14, [(0x24, 0x64)])
        + g711_pes(0x54, SAMPLES)
    )

    [pkt] = read_all(stream)

    assert pkt.payloadType == PayloadType.PCMU
    assert bytes(pkt.payload) == SAMPLES


def test_streams_of_every_program_are_registered():
    reader = TSReader()
    reader.setBuffer(
        pat([(1, 0x12), (2, 0x13), (3, 0x14)])
        + pmt(0x12, [(0x24, 0x44)])
        + pmt(0x13, [(0x91, 0x54)])
        + pmt(0x14, [(0x24, 0x64)])
    )
    reader.getPacket()

    assert {pid: pes.StreamType for pid, pes in reader.pes.items()} == {
        0x44: 0x24,
        0x54: 0x91,
        0x64: 0x24,
    }
