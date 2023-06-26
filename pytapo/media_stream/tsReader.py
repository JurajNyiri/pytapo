from pytapo.media_stream.pes import PES


class TSReader:
    PacketSize = 188
    SyncByte = 0x47
    const_pid_null_packet = 0x1FFF
    const_has_adaption_field = 0b0010_0000
    const_pid_pat = 0
    const_crc_size = 4

    def __init__(self):
        self.b = bytearray()
        self.i = 0  # read position
        self.s = self.PacketSize  # end position
        self.pmt = 0
        self.pes = {}

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

        self.skip(4)  # Skipping Table ID extension and flags
        self.skip(2)  # Skipping Section number and Last section number

    def read_packet_content(self):
        self.skip(1)  # Sync byte

        pid = self.read_uint16() & 0x1FFF  # PID
        flag = self.read_byte()  # flags...

        if pid == self.const_pid_null_packet:
            return None

        if flag & self.const_has_adaption_field != 0:
            ad_size = self.read_byte()  # Adaptation field length
            if ad_size > self.PacketSize - 6:
                print("WARNING: mpegts: wrong adaptation size")
                return None
            self.skip(ad_size)

        return pid

    def handle_pat(self):
        self.read_psi_header()

        while self.left() > self.const_crc_size:
            p_num = self.read_uint16()
            p_pid = self.read_uint16() & 0x1FFF
            if p_num != 0:
                self.pmt = p_pid

        self.skip(self.const_crc_size)  # CRC32

    def handle_pmt(self):
        self.read_psi_header()

        pes_pid = self.read_uint16() & 0x1FFF  # ? PCR PID
        p_size = self.read_uint16() & 0x03FF  # ? 0x0FFF
        self.skip(p_size)

        self.pes = {}

        while self.left() > self.const_crc_size:
            stream_type = self.read_byte()
            pes_pid = self.read_uint16() & 0x1FFF  # Elementary PID
            i_size = self.read_uint16() & 0x03FF  # ? 0x0FFF
            self.skip(i_size)

            self.pes[pes_pid] = PES()
            self.pes[pes_pid].StreamType = stream_type

        self.skip(self.const_crc_size)  # ? CRC32

    def getPacket(self):
        while self.sync():
            pid = self.read_packet_content()
            if pid is None:
                continue

            if pid == self.const_pid_pat:
                if self.pmt != 0:  # already processed
                    continue
                self.handle_pat()
                continue

            if pid == self.pmt:
                if bool(self.pes):  # already processed
                    continue
                self.handle_pmt()
                continue

            if not bool(self.pes) or pid not in self.pes:
                continue  # unknown PID or no PES

            pes_pid = self.pes[pid]
            if pes_pid.Payload is None:
                # PES Packet start code prefix
                if (
                    self.read_byte() != 0
                    or self.read_byte() != 0
                    or self.read_byte() != 1
                ):
                    continue

                # read stream ID and total payload size
                pes_pid.StreamID = self.read_byte()
                pes_pid.SetBuffer(self.read_uint16(), self.Bytes())
            else:
                pes_pid.AppendBuffer(self.Bytes())

            if pkt := pes_pid.GetPacket():
                return pkt

        return None

    def Bytes(self):
        return self.b[self.i: self.PacketSize]

    def sync(self):
        # drop previous readed packet
        if self.i != 0:
            self.b = self.b[self.PacketSize:]
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
