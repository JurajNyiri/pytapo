from rtp import RTP, PayloadType
from pytapo.media_stream._utils import parse_time, annexB2AVC


class PES:
    StreamType = None
    StreamID = None
    Payload = None
    Mode = None
    Size = None
    Sequence = 0
    Timestamp = 0
    minHeaderSize = 3
    StreamTypePrivate = 0x06
    StreamTypeAAC = 0x0F
    StreamTypeH264 = 0x1B
    StreamTypePCMATapo = 0x90
    ModeUnknown = 0
    ModeSize = 1
    ModeStream = 2

    def SetBuffer(self, size: int, b: bytes):

        if size == 0:
            optSize = b[2]  # optional fields
            b = b[self.minHeaderSize + optSize :]
            b = bytes(b)
            if self.StreamType == self.StreamTypeH264 and b.startswith(
                b"\x00\x00\x00\x01\x09"
            ):
                self.Mode = self.ModeStream
                b = b[5:]

            if self.Mode == self.ModeUnknown:
                print("WARNING: mpegts: unknown zero-size stream")

        else:
            self.Mode = self.ModeSize
            self.Size = size

        self.Payload = b

    def AppendBuffer(self, b: bytes):
        self.Payload += bytes(b)

    def GetPacket(self) -> RTP:
        pkt = None
        if self.Mode == self.ModeSize:
            left = self.Size - len(self.Payload)
            if left > 0:
                return None

            if left < 0:
                # todo: uncomment and fix
                # print("WARNING: mpegts: buffer overflow")
                self.Payload = None
                return None

            # first byte also flags
            flags = self.Payload[1]
            optSize = self.Payload[2]  # optional fields
            payload = self.Payload[self.minHeaderSize + optSize :]

            if self.StreamType == self.StreamTypeH264:
                ts = 0
                hasPTS = 0b1000_0000
                if flags & hasPTS:
                    ts = parse_time(self.Payload[self.minHeaderSize :])

                streamType = None
                for var_name, var_value in vars(PayloadType).items():
                    if var_value == self.StreamType:
                        streamType = PayloadType[var_name]
                pkt = RTP(
                    payload=annexB2AVC(payload), payloadType=streamType, timestamp=ts,
                )
            elif self.StreamType == self.StreamTypePCMATapo:
                self.Sequence += 1
                self.Timestamp += len(payload)

                streamType = None
                for var_name, var_value in vars(PayloadType).items():
                    if var_value == self.StreamType:
                        streamType = PayloadType[var_name]

                pkt = RTP(
                    version=2,
                    sequenceNumber=self.Sequence,
                    timestamp=self.Timestamp,
                    payload=bytearray(payload),
                    payloadType=PayloadType.PCMA,  # todo is this correct?
                )

            else:
                pkt = None

            self.Payload = None

        elif self.Mode == self.ModeStream:
            # todo: implement
            print("TODO IMPLEMENT is this needed?")
            raise Exception("TODO IMPLEMENT, needed?")
        else:
            self.Payload = None
        return pkt
