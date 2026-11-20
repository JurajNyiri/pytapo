"""Tapo's speaker backchannel (PCMA/8000 in MPEG-TS).

Protocol reference: https://github.com/AlexxIT/go2rtc/tree/master/pkg/tapo
"""

import asyncio
import json

from ._utils import StreamType


def _psi_packet(pid, section):
    """Add the MPEG-2 CRC and wrap a PAT/PMT section in one TS packet."""
    crc = 0xFFFFFFFF
    for value in section:
        crc ^= value << 24
        for _ in range(8):
            crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    packet = bytes((0x47, 0x40 | (pid >> 8), pid & 0xFF, 0x10, 0))
    packet += section + crc.to_bytes(4, "big")
    return packet.ljust(188, b"\xff")


class Talk:
    """Send encoded mono A-law audio at 8 kHz to a camera's speaker.

    Use as an async context manager and pass each audio chunk to ``write``.
    Audio must arrive at its playback rate; this class does not pace it.
    """

    def __init__(self, tapo):
        self.tapo = tapo
        self.session = None
        self.responses = None
        self.session_id = None
        self._counter = 0
        self._samples = 0
        self._locked = False

    async def __aenter__(self):
        # All entities for one camera share its controller and speaker.
        if not hasattr(self.tapo, "_talk_lock"):
            self.tapo._talk_lock = asyncio.Lock()
        if self.tapo._talk_lock.locked():
            raise RuntimeError("The camera speaker is already in use")
        await self.tapo._talk_lock.acquire()
        self._locked = True
        try:
            self.session = await asyncio.to_thread(
                self.tapo.getMediaSession, StreamType.Stream
            )
            await self.session.start()
            self.responses = self.session.transceive(
                json.dumps(
                    {
                        "type": "request",
                        "seq": 1,
                        "params": {"talk": {"mode": "aec"}, "method": "get"},
                    }
                ),
                no_data_timeout=5,
            )
            async with asyncio.timeout(5):
                async for response in self.responses:
                    if response.mimetype != "application/json":
                        continue
                    data = response.json_data
                    params = data.get("params") or {}
                    error = params.get("error_code", data.get("error_code", 0))
                    if error not in (0, None):
                        raise RuntimeError(f"Camera refused talk request: {error}")
                    if data.get("type") == "response":
                        self.session_id = response.session
                        break
            if self.session_id is None:
                raise RuntimeError("Camera did not open a talk session")
            # PAT: program 1 -> PMT PID 0x1000. PMT: PCMA (0x90), PID 0x100.
            header = _psi_packet(0, bytes.fromhex("00b00d0001c100000001f000"))
            header += _psi_packet(
                0x1000, bytes.fromhex("02b0120001c10000fffff00090e100f000")
            )
            await self.session.send_audio(header, self.session_id)
            return self
        except BaseException:
            await self.close()
            raise

    async def write(self, audio):
        if self.session_id is None:
            raise RuntimeError("Talk session is not open")
        if not audio:
            return
        if len(audio) > 65527:
            raise ValueError("Audio chunk is too large for one PES packet")
        pts = (self._samples * 90000 // 8000) & ((1 << 33) - 1)
        timestamp = bytes(
            (
                0x21 | ((pts >> 29) & 0x0E),
                (pts >> 22) & 0xFF,
                1 | ((pts >> 14) & 0xFE),
                (pts >> 7) & 0xFF,
                1 | ((pts << 1) & 0xFE),
            )
        )
        payload = b"\x00\x00\x01\xc0" + (len(audio) + 8).to_bytes(2, "big")
        payload += b"\x80\x80\x05" + timestamp + audio
        packets = bytearray()
        first = True
        while payload:
            chunk, payload = payload[:184], payload[184:]
            flags = 0x10 if len(chunk) == 184 else 0x30
            packets.extend((0x47, 0x41 if first else 0x01, 0, flags | self._counter))
            if len(chunk) < 184:
                padding = 183 - len(chunk)
                packets.append(padding)
                if padding:
                    packets.extend(b"\x00" + b"\xff" * (padding - 1))
            packets.extend(chunk)
            self._counter = (self._counter + 1) & 0x0F
            first = False
        await self.session.send_audio(bytes(packets), self.session_id)
        self._samples += len(audio)

    async def __aexit__(self, *args):
        await self.close()

    async def close(self):
        self.session_id = None
        try:
            if self.responses is not None:
                await self.responses.aclose()
        finally:
            try:
                if self.session is not None:
                    await self.session.close()
            finally:
                if self._locked:
                    self.tapo._talk_lock.release()
                    self._locked = False
