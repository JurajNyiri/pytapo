"""
Experimental code rewritten from go2rtc (go) to pytapo (python).

https://github.com/AlexxIT/go2rtc/blob/master/pkg/tapo/client.go#L174
"""

from pytapo import Tapo
import json
import asyncio
from rtp import RTP, PayloadType
import sys
import os

# logging.basicConfig(level=logging.DEBUG)
# change variables here
host = os.environ.get("host")  # change to camera IP
user = os.environ.get("user")  # your username
password = os.environ.get("password")  # your password
password_cloud = os.environ.get("password_cloud")  # set to your cloud password

tapo = Tapo(host, user, password, password_cloud)

devID = tapo.getBasicInfo()["device_info"]["basic_info"]["dev_id"]


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
        self.Payload += b

    def GetPacket(self) -> RTP:
        if self.Mode == self.ModeSize:
            left = self.Size - len(self.Payload)
            if left > 0:
                return None

            if left < 0:
                print("WARNING: mpegts: buffer overflow")
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
                )

            else:
                pkt = None

            self.Payload = None

        elif self.Mode == self.ModeStream:
            # todo: implement
            print("TODO IMPLEMENT is this needed?")
            sys.exit(0)
            raise Exception("TODO IMPLEMENT, needed?")
            pass
        else:
            self.Payload = None

        return pkt


class Reader:
    b = bytearray  # packets buffer
    i = 0  # read position
    s = 0  # end position
    pmt = 0
    pes = {}
    PacketSize = 188
    SyncByte = 0x47

    def __init__(self):
        pass

    def setBuffer(self, body: bytearray):
        self.b = body
        self.i = 0
        self.s = self.PacketSize

    def skip(self, i):
        self.i += i

    def read_uint16(self):
        i = (self.b[self.i] << 8) | self.b[self.i + 1]
        self.i += 2
        return i

    def set_size(self, size):
        self.s = self.i + size

    def left(self):
        return self.s - self.i

    def read_byte(self):
        b = self.b[self.i]
        self.i += 1
        return b

    def read_psi_header(self):
        pointer = self.read_byte()  # Pointer field
        self.skip(pointer)  # Pointer filler bytes

        self.skip(1)  # Table ID
        size = self.read_uint16() & 0x03FF  # Section length
        self.set_size(size)

        self.skip(2)  # Table ID extension
        self.skip(1)  # flags...
        self.skip(1)  # Section number
        self.skip(1)  # Last section number

    def getPacket(self):
        while self.sync():
            self.skip(1)  # Sync byte

            pid = self.read_uint16() & 0x1FFF  # PID
            flag = self.read_byte()  # flags...

            const_pid_null_packet = 0x1FFF
            if pid == const_pid_null_packet:
                print("null")
                continue

            const_has_adaption_field = 0b0010_0000
            if flag & const_has_adaption_field != 0:
                ad_size = self.read_byte()  # Adaptation field length
                if ad_size > self.PacketSize - 6:
                    print("WARNING: mpegts: wrong adaptation size")
                    continue
                self.skip(ad_size)

            # PAT: Program Association Table
            const_pid_pat = 0
            if pid == const_pid_pat:
                # already processed
                if self.pmt != 0:
                    continue

                self.read_psi_header()

                const_crc_size = 4
                while self.left() > const_crc_size:
                    p_num = self.read_uint16()
                    p_pid = self.read_uint16() & 0x1FFF
                    if p_num != 0:
                        self.pmt = p_pid

                self.skip(4)  # CRC32
                continue

            # PMT : Program Map Table
            if pid == self.pmt:
                # already processed
                if bool(self.pes) is True:
                    continue

                self.read_psi_header()

                pes_pid = self.read_uint16() & 0x1FFF  # ? PCR PID
                p_size = self.read_uint16() & 0x03FF  # ? 0x0FFF
                self.skip(p_size)

                self.pes = {}

                const_crc_size = 4
                while self.left() > const_crc_size:
                    stream_type = self.read_byte()
                    pes_pid = self.read_uint16() & 0x1FFF  # Elementary PID
                    i_size = self.read_uint16() & 0x03FF  # ? 0x0FFF
                    self.skip(i_size)

                    self.pes[pes_pid] = PES()
                    self.pes[pes_pid].StreamType = stream_type

                self.skip(4)  # ? CRC32
                continue

            if bool(self.pes) is False:
                continue

            if pid not in self.pes:
                continue  # unknown PID

            # print(self.i)
            # print(pid)
            # print(self.pes)
            # print(self.pes[pid])

            # print("pid:" + str(pid))
            # print(self.b)
            if self.pes[pid].Payload is None:
                # print("nil")
                # print(self.i)
                # print(self.b)
                # print(self.b[self.i])
                # print(self.b[self.i + 1])
                # print(self.b[self.i + 2])
                # PES Packet start code prefix
                if (
                    self.read_byte() != 0
                    or self.read_byte() != 0
                    or self.read_byte() != 1
                ):
                    print("FAIL: IT SHOULD NEVER GET HERE")
                    sys.exit(0)
                    continue

                # read stream ID and total payload size
                self.pes[pid].StreamID = self.read_byte()
                self.pes[pid].SetBuffer(self.read_uint16(), self.Bytes())
            else:
                self.pes[pid].AppendBuffer(self.Bytes())
            # print("getPacket - 7")

            if pkt := self.pes[pid].GetPacket():
                return pkt
            # print("getPacket - 8")

        return None

    def Bytes(self):
        return self.b[self.i : self.PacketSize]

    def sync(self):
        # drop previous readed packet
        if self.i != 0:
            self.b = self.b[self.PacketSize :]
            self.i = 0
            self.s = self

        # if packet available
        if len(self.b) < self.PacketSize:
            return False

        # if data starts from sync byte
        if self.b[0] == self.SyncByte:
            return True

        while len(self.b) >= self.PacketSize:
            if self.b[0] == self.SyncByte:
                return True
            self.b = self.b[1:]

        return False


tsReader = Reader()


async def download_async():
    print("Starting...")
    mediaSession = tapo.getMediaSession()
    async with mediaSession:
        payload2 = {
            "params": {
                "preview": {
                    "audio": ["default"],
                    "channels": [0],
                    "deviceId": devID,
                    "resolutions": ["HD"],
                },
                "method": "get",
            },
            "type": "request",
        }

        payload = json.dumps(payload2)
        output = b""
        dataChunks = 0
        fileName = "./output/stream.mp4"
        async for resp in mediaSession.transceive(payload):
            if resp.mimetype == "video/mp2t":
                # if len(resp.plaintext) != 376:
                # output += resp.plaintext
                # print(dataChunks)
                if resp.ciphertext:
                    print("Size before decrypt: " + str(len(resp.ciphertext)))
                # print(list(resp.ciphertext)[0:5])

                print("Size after decrypt: " + str(len(resp.plaintext)))
                print(list(resp.plaintext)[0:5])
                # print(list(resp.plaintext))

                tsReader.setBuffer(list(resp.plaintext))
                # output += resp.plaintext

                pkt = tsReader.getPacket()
                if pkt:
                    print("PACKET size: " + str(len(list(pkt.payload))))
                    print(pkt)
                    print("____")

                dataChunks += 1
            else:
                print(resp.plaintext)
            if dataChunks > 1000:
                break
            print("____")
        file = open(fileName, "wb")
        file.write(output)
        file.close()
        print("Saving to " + fileName + "...")


loop = asyncio.get_event_loop()
loop.run_until_complete(download_async())
