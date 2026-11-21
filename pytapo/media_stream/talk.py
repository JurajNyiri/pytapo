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
    Audio passed to ``write`` must arrive at its playback rate.
    Playback sessions can supply an async ``on_interrupt`` callback so live
    talk can stop them before taking the speaker.
    """

    def __init__(self, tapo, *, on_interrupt=None):
        self.tapo = tapo
        self._on_interrupt = on_interrupt
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
        current = getattr(self.tapo, "_talk_session", None)
        if (
            self.tapo._talk_lock.locked()
            and current is not None
            and current._on_interrupt is not None
            and self._on_interrupt is None
        ):
            # Live talk takes priority over media. Finish its cleanup even if
            # the browser disconnects while waiting for the speaker.
            await asyncio.shield(current._on_interrupt())
        if self.tapo._talk_lock.locked():
            raise RuntimeError("The camera speaker is already in use")
        await self.tapo._talk_lock.acquire()
        self._locked = True
        self.tapo._talk_session = self
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

    async def play(self, source, *, ffmpeg="ffmpeg"):
        """Decode a file or URL with FFmpeg and send it at its playback rate.

        Call inside an open Talk context. Cancelling playback stops FFmpeg;
        the context manager owns the speaker connection.
        """
        if self.session_id is None:
            raise RuntimeError("Talk session is not open")
        start = asyncio.create_task(
            asyncio.create_subprocess_exec(
                ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                "-rw_timeout", "10000000", "-i", source,
                "-vn", "-sn", "-dn",
                # Give the camera speaker time to start before the clip.
                "-af", "adelay=1000:all=1", "-ac", "1", "-ar", "8000",
                "-c:a", "pcm_alaw", "-f", "alaw", "pipe:1",
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        )
        process = None
        try:
            # Retain the process if cancellation arrives while it is starting.
            process = await asyncio.shield(start)
            loop = asyncio.get_running_loop()
            deadline = loop.time()
            samples = 0
            while audio := await asyncio.wait_for(process.stdout.read(160), 15):
                await asyncio.sleep(max(0, deadline - loop.time()))
                await asyncio.wait_for(self.write(audio), 5)
                samples += len(audio)
                deadline = max(deadline + len(audio) / 8000, loop.time())
            await asyncio.sleep(max(0, deadline - loop.time()))
            code = await asyncio.wait_for(process.wait(), 5)
            if code != 0 or not samples:
                raise RuntimeError(
                    f"FFmpeg could not decode the audio (exit code {code})"
                )
        finally:
            if process is None:
                process = await start
            if process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.communicate(), 3)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.communicate()

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
                    if getattr(self.tapo, "_talk_session", None) is self:
                        self.tapo._talk_session = None
                    self.tapo._talk_lock.release()
                    self._locked = False
