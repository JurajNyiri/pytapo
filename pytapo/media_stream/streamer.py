import json
import os
import asyncio
import subprocess

HLS_TIME = 1
HLS_LIST_SIZE = 3
HLS_FLAGS = "delete_segments+append_list"


class Streamer:
    FRESH_RECORDING_TIME_SECONDS = 60
    CHUNK_SAVE_INTERVAL = 150  # Save after 10 chunks

    def __init__(
        self,
        tapo,
        callbackFunction,
        outputDirectory="./",
        quality="HD",
        window_size=None,
        fileName=None,
        logLevel="debug",
        probeSize=32,
        analyzeDuration=0,
        includeAudio=False,
        mode="pipe",
    ):
        self.currentAction = "Idle"
        self.callbackFunction = callbackFunction
        self.tapo = tapo
        self.fileName = fileName or "stream_output.m3u8"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 50
        self.hls_task = None
        self.quality = quality
        self.running = False
        self.logLevel = logLevel
        self.probeSize = probeSize
        self.analyzeDuration = analyzeDuration
        self.includeAudio = includeAudio
        self.mode = mode.lower()
        # initialise in case audio is disabled
        self.audio_r = None
        self.audio_w = None
        self._ts_buffer = bytearray()
        self._audio_buffer = bytearray()

    async def start(self):
        if self.mode == "hls":
            return await self.start_hls()
        return await self.start_pipe()

    async def start_pipe(self):
        """Starts ffmpeg that writes MPEG‑TS to stdout"""
        self.currentAction = "FFMpeg Starting (pipe)"

        pipe_cmd = [
            "ffmpeg",
            "-loglevel",
            f"{self.logLevel}",
            "-probesize",
            f"{self.probeSize}",
            "-analyzeduration",
            f"{self.analyzeDuration}",
            "-f",
            "mpegts",
            "-i",
            "pipe:0",
        ]

        # pass_fds list depends on whether audio is enabled
        pass_fds = ()

        if self.includeAudio:
            self.audio_r, self.audio_w = os.pipe()
            pass_fds = (self.audio_r,)
            pipe_cmd += [
                "-f",
                "alaw",
                "-ar",
                "8000",
                "-i",
                f"/dev/fd/{self.audio_r}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        else:
            pipe_cmd += [
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
            ]

        pipe_cmd += [
            "-f",
            "mpegts",
            "pipe:1",
        ]

        self.hlsProcess = await asyncio.create_subprocess_exec(
            *pipe_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=pass_fds,
        )

        # asyncio.create_task(self._drain_stdout(self.hlsProcess.stdout))
        asyncio.create_task(self._print_ffmpeg_logs(self.hlsProcess.stderr))

        self.running = True
        if self.hls_task is None or self.hls_task.done():
            self.hls_task = asyncio.create_task(self._stream_to_ffmpeg())

        read_fd = self.hlsProcess.stdout._transport.get_extra_info("pipe").fileno()
        return {
            "ffmpegProcess": self.hlsProcess,
            "streamProcess": self.hls_task,
            "read_fd": read_fd,  # use as "pipe:<fd>"
        }

    async def _drain_stdout(self, stdout: asyncio.StreamReader):
        """Read & discard all bytes from ffmpeg stdout."""
        try:
            while await stdout.read(65536):
                pass
        except asyncio.CancelledError:
            pass

    async def start_hls(self):
        """Starts HLS stream using ffmpeg without writing intermediate files."""
        self.currentAction = "FFMpeg Starting"
        os.makedirs(self.outputDirectory, exist_ok=True)

        # Clean up old HLS files
        for f in os.listdir(self.outputDirectory):
            os.remove(os.path.join(self.outputDirectory, f))

        hls_cmd = [
            "ffmpeg",
            "-loglevel",
            f"{self.logLevel}",
            "-probesize",
            f"{self.probeSize}",
            "-analyzeduration",
            f"{self.analyzeDuration}",
            "-f",
            "mpegts",
            "-i",
            "pipe:0",  # Video input from pipe
        ]

        pass_fds = ()

        if self.includeAudio:
            self.audio_r, self.audio_w = os.pipe()
            pass_fds = (self.audio_r,)
            hls_cmd += [
                "-f",
                "alaw",
                "-ar",
                "8000",
                "-i",
                f"/dev/fd/{self.audio_r}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
            ]
        else:
            hls_cmd += [
                "-map",
                "0:v:0",
                "-c:v",
                "copy",
            ]

        hls_cmd += [
            "-f",
            "hls",
            "-hls_time",
            f"{HLS_TIME}",
            "-hls_list_size",
            f"{HLS_LIST_SIZE}",
            "-hls_flags",
            HLS_FLAGS,
            os.path.join(self.outputDirectory, self.fileName),
        ]

        self.hlsProcess = await asyncio.create_subprocess_exec(
            *hls_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # Capture stderr for logs
            pass_fds=pass_fds,  # Pass the read end of the pipe only if audio enabled
        )

        asyncio.create_task(self._print_ffmpeg_logs(self.hlsProcess.stderr))

        self.running = True
        if self.hls_task is None or self.hls_task.done():
            self.hls_task = asyncio.create_task(self._stream_to_ffmpeg())
        return {"ffmpegProcess": self.hlsProcess, "streamProcess": self.hls_task}

    async def _print_ffmpeg_logs(self, stderr):
        """Reads and prints FFmpeg logs asynchronously."""
        while True:
            line = await stderr.readline()
            if not line:
                break
            self.callbackFunction(
                {
                    "currentAction": self.currentAction,
                    "ffmpegLog": line.decode().strip(),
                }
            )

    async def _stream_to_ffmpeg(self):
        """
        Forward camera preview to FFmpeg.

        ▸ Video (MPEG‑TS, 188‑byte cells) → ffmpeg.stdin
        ▸ Optional A‑law audio           → dedicated pipe (self.audio_w)

        When audio is enabled we never call `await stdin.drain()` because
        FFmpeg blocks until it has data on *both* inputs; that would dead‑lock
        the coroutine.  In video‑only mode we keep the drain to avoid filling
        the kernel pipe.
        """
        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(self.window_size)
        self.currentAction = "Streaming"

        async with mediaSession:
            payload = json.dumps(
                {
                    "type": "request",
                    "seq": 1,
                    "params": {
                        "preview": {
                            "audio": ["default"],
                            "channels": [0],
                            "resolutions": [self.quality],
                        },
                        "method": "get",
                    },
                }
            )

            async for resp in mediaSession.transceive(payload):
                # ----------------------------------------------------------------
                # 1.  Stop on cancellation
                # ----------------------------------------------------------------
                if not self.running:
                    break

                if resp.mimetype != "video/mp2t":
                    continue

                # ----------------------------------------------------------------
                # 2.  Optional audio
                # ----------------------------------------------------------------
                if self.includeAudio and resp.audioPayload:
                    self._audio_buffer += resp.audioPayload

                    # Flush complete 160‑byte A‑law frames (20 ms @ 8 kHz)
                    while len(self._audio_buffer) >= 160:
                        frame = self._audio_buffer[:160]
                        self._audio_buffer = self._audio_buffer[160:]
                        try:
                            os.write(self.audio_w, frame)
                        except OSError:
                            break

                # ----------------------------------------------------------------
                # 3.  Video – re‑assemble & byte‑align to 188‑byte TS cells
                # ----------------------------------------------------------------
                self._ts_buffer += resp.plaintext

                # ── drop leading garbage until the first real sync byte (0x47) ──
                while len(self._ts_buffer) >= 188 and self._ts_buffer[0] != 0x47:
                    pos = self._ts_buffer.find(0x47, 1)
                    if pos == -1:
                        # no sync byte in current buffer – wait for more data
                        self._ts_buffer.clear()
                        break
                    self._ts_buffer = self._ts_buffer[pos:]

                # ── forward only full, correctly aligned 188‑byte packets ───────
                while len(self._ts_buffer) >= 188:
                    packet = self._ts_buffer[:188]
                    self._ts_buffer = self._ts_buffer[188:]
                    self.hlsProcess.stdin.write(packet)

                # ----------------------------------------------------------------
                # 4.  Back‑pressure only in video‑only mode
                # ----------------------------------------------------------------
                if not self.includeAudio:
                    await self.hlsProcess.stdin.drain()

    async def stop_hls(self):
        """Stops the HLS streaming process."""
        self.currentAction = "Stopping HLS..."
        self.running = False
        if self.hls_task:
            self.hls_task.cancel()
            try:
                await self.hls_task
            except asyncio.CancelledError:
                pass
