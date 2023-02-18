from pytapo.media_stream.pes import PES


class TSReader:
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
