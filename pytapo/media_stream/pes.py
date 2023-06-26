from enum import Enum
import logging
from rtp import RTP, PayloadType
from pytapo.media_stream._utils import parse_time, annexB2AVC

logging.basicConfig(level=logging.DEBUG)


class StreamType(Enum):
    Private = 0x06
    AAC = 0x0F
    H264 = 0x1B
    PCMATapo = 0x90


class PES:
    ModeUnknown = 0
    ModeSize = 1
    ModeStream = 2
    minHeaderSize = 3

    def __init__(self):
        self.StreamType = None
        self.StreamID = None
        self.Payload = b""
        self.Mode = None
        self.Size = None
        self.Sequence = 0
        self.Timestamp = 0

    def get_payload_type(self, stream_type):
        payload_type_mapping = {
            StreamType.H264: PayloadType.H264,
            StreamType.PCMATapo: PayloadType.PCMA,
            # add other mappings here
        }
        return payload_type_mapping.get(stream_type)

    def SetBuffer(self, size: int, b: bytes) -> None:
        if size == 0:
            optSize = b[2]  # optional fields
            b = b[self.minHeaderSize + optSize :]
            if self.StreamType == StreamType.H264 and b.startswith(
                b"\x00\x00\x00\x01\x09"
            ):
                self.Mode = self.ModeStream
                b = b[5:]

            if self.Mode == self.ModeUnknown:
                logging.warning("mpegts: unknown zero-size stream")

        else:
            self.Mode = self.ModeSize
            self.Size = size

        self.Payload = b

    def AppendBuffer(self, b: bytes) -> None:
        self.Payload += b

    def GetPacket(self) -> RTP:
        pkt = None
        if self.Mode == self.ModeSize:
            left = self.Size - len(self.Payload)
            if left > 0:
                return None

            if left < 0:
                logging.warning("mpegts: buffer overflow")
                self.Payload = None
                return None

            optSize = self.Payload[2]  # optional fields
            payload = self.Payload[self.minHeaderSize + optSize :]

            if self.StreamType == StreamType.H264:
                pkt = self.generate_RTP(payload)
            elif self.StreamType == StreamType.PCMATapo:
                self.Sequence += 1
                self.Timestamp += len(payload)

                stream_type = self.get_payload_type(self.StreamType)

                pkt = RTP(
                    version=2,
                    sequenceNumber=self.Sequence,
                    timestamp=self.Timestamp,
                    payload=payload,
                    payloadType=stream_type,
                )

            else:
                pkt = None

            self.Payload = None

        elif self.Mode == self.ModeStream:
            raise NotImplementedError("Stream mode not implemented")

        else:
            self.Payload = None

        return pkt

    def generate_RTP(self, payload):
        hasPTS = 0b1000_0000
        # first byte also flags
        flags = self.Payload[1]
        ts = parse_time(self.Payload[self.minHeaderSize :]) if flags & hasPTS else 0
        stream_type = self.get_payload_type(self.StreamType)
        return RTP(
            payload=annexB2AVC(payload),
            payloadType=stream_type,
            timestamp=ts,
        )
