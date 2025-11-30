import json
import os
import asyncio
import subprocess
from ._utils import StreamType

HLS_TIME = 1
HLS_LIST_SIZE = 3
HLS_FLAGS = "delete_segments+append_list"


class Streamer:
    def __init__(
        self,
        tapo,
        logFunction=None,
        outputDirectory="./",
        removeFilesInOutputDirectory=False,
        quality="HD",
        window_size=None,
        fileName=None,
        logLevel="debug",
        probeSize=32,
        analyzeDuration=0,
        includeAudio=False,
        mode="pipe",
        ff_args={},
    ):
        self.currentAction = "Idle"
        self.logFunction = logFunction
        self.tapo = tapo
        self.fileName = fileName or "stream_output.m3u8"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 50
        self.stream_task = None
        self.quality = quality
        self.running = False
        self.logLevel = logLevel
        self.probeSize = probeSize
        self.analyzeDuration = analyzeDuration
        self.includeAudio = includeAudio
        self.mode = mode.lower()
        self.removeFilesInOutputDirectory = removeFilesInOutputDirectory
        self.audio_r = None
        self.audio_w = None
        self.audio_format = None
        self.audio_rate = None
        self._ts_buffer = bytearray()
        self._audio_buffer = bytearray()
        self.ff_args = ff_args

    async def _init_audio_params(self):
        if not self.includeAudio:
            return
        if self.audio_format is not None and self.audio_rate is not None:
            return

        audio_format = "alaw"
        audio_rate = 8000

        try:
            loop = asyncio.get_event_loop()
            audio_config = await loop.run_in_executor(None, self.tapo.getAudioConfig)
            microphone = audio_config.get("audio_config", {}).get("microphone", {})
            encode_type = str(microphone.get("encode_type", "")).lower()
            if "ulaw" in encode_type:
                audio_format = "mulaw"
            elif "alaw" in encode_type:
                audio_format = "alaw"

            sampling_rate = microphone.get("sampling_rate")
            if sampling_rate is not None:
                audio_rate = int(sampling_rate) * 1000
        except Exception:
            # fall back to defaults if detection fails
            pass

        self.audio_format = audio_format
        self.audio_rate = audio_rate

    async def start(self):
        self.currentAction = "FFMpeg Starting"

        if self.mode == "hls":
            os.makedirs(self.outputDirectory, exist_ok=True)
            if self.removeFilesInOutputDirectory:
                for f in os.listdir(self.outputDirectory):
                    os.remove(os.path.join(self.outputDirectory, f))

        if self.includeAudio:
            await self._init_audio_params()

        cmd = [
            "ffmpeg",
            "-loglevel",
            self.ff_args.get("-loglevel", f"{self.logLevel}"),
            "-probesize",
            self.ff_args.get("-probesize", f"{self.probeSize}"),
            "-analyzeduration",
            self.ff_args.get("-analyzeduration", f"{self.analyzeDuration}"),
            "-f",
            "mpegts",
            "-i",
            "pipe:0",
        ]

        if "-frames:v" in self.ff_args:
            cmd += [
                "-frames:v",
                self.ff_args["-frames:v"],
            ]

        pass_fds = ()

        if self.includeAudio:
            self.audio_r, self.audio_w = os.pipe()
            pass_fds = (self.audio_r,)
            cmd += [
                "-f",
                self.audio_format or "alaw",
                "-ar",
                f"{self.audio_rate or 8000}",
                "-i",
                f"/dev/fd/{self.audio_r}",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                self.ff_args.get("-c:v", "copy"),
            ]
            if "-vsync" in self.ff_args:
                cmd += [
                    "-vsync",
                    self.ff_args["-vsync"],
                ]
            cmd += [
                "-c:a",
                self.ff_args.get("-c:a", "aac"),
                "-b:a",
                self.ff_args.get("-b:a", "128k"),
            ]
        else:
            cmd += ["-map", "0:v:0"]
            if "-vsync" in self.ff_args:
                cmd += [
                    "-vsync",
                    self.ff_args["-vsync"],
                ]
            cmd += ["-c:v", self.ff_args.get("-c:v", "copy")]

        if self.mode == "hls":
            cmd += [
                "-f",
                self.ff_args.get("-f", "hls"),
                "-hls_time",
                f"{HLS_TIME}",
                "-hls_list_size",
                f"{HLS_LIST_SIZE}",
                "-hls_flags",
                HLS_FLAGS,
                os.path.join(self.outputDirectory, self.fileName),
            ]
        else:
            cmd += [
                "-f",
                self.ff_args.get("-f", "mpegts"),
                "pipe:1",
            ]

        self.streamProcess = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=pass_fds,
        )

        asyncio.create_task(self._print_ffmpeg_logs(self.streamProcess.stderr))

        self.running = True
        if self.stream_task is None or self.stream_task.done():
            self.stream_task = asyncio.create_task(self._stream_to_ffmpeg())

        read_fd = None
        if self.mode == "pipe":
            read_fd = self.streamProcess.stdout._transport.get_extra_info(
                "pipe"
            ).fileno()

        return {
            "ffmpegProcess": self.streamProcess,
            "streamProcess": self.stream_task,
            "read_fd": read_fd,
        }

    async def _print_ffmpeg_logs(self, stderr):
        while True:
            line = await stderr.readline()
            if not line:
                break
            if self.logFunction is not None:
                self.logFunction(
                    {
                        "currentAction": self.currentAction,
                        "ffmpegLog": line.decode().strip(),
                    }
                )

    async def _stream_to_ffmpeg(self):
        mediaSession = self.tapo.getMediaSession(StreamType.Stream)
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
                if not self.running:
                    break

                if resp.mimetype != "video/mp2t":
                    continue

                # Audio - Flush complete 160‑byte A‑law frames (20 ms @ 8 kHz)
                if self.includeAudio and resp.audioPayload:
                    self._audio_buffer += resp.audioPayload

                    while len(self._audio_buffer) >= 160:
                        frame = self._audio_buffer[:160]
                        self._audio_buffer = self._audio_buffer[160:]
                        try:
                            os.write(self.audio_w, frame)
                        except OSError:
                            break

                # Video – re‑assemble & byte‑align to 188‑byte TS cells
                self._ts_buffer += resp.plaintext

                # drop leading garbage until the first real sync byte (0x47)
                while len(self._ts_buffer) >= 188 and self._ts_buffer[0] != 0x47:
                    pos = self._ts_buffer.find(0x47, 1)
                    if pos == -1:
                        # no sync byte in current buffer – wait for more data
                        self._ts_buffer.clear()
                        break
                    self._ts_buffer = self._ts_buffer[pos:]

                # forward only full, correctly aligned 188‑byte packets
                while len(self._ts_buffer) >= 188:
                    packet = self._ts_buffer[:188]
                    self._ts_buffer = self._ts_buffer[188:]
                    self.streamProcess.stdin.write(packet)

                if not self.includeAudio:
                    await self.streamProcess.stdin.drain()

    async def stop(self):
        self.currentAction = "Stopping stream"
        self.running = False
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass
