import json
import os
import asyncio
import subprocess

# Add the Queue import
from asyncio import Queue

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
        probeSize=131072,
        analyzeDuration=0,
        includeAudio=False,
        mode="pipe",
    ):
        self.currentAction = "Idle"
        self.logFunction = logFunction
        self.tapo = tapo
        self.fileName = fileName or "stream_output.m3u8"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 50
        self.stream_task = None
        # NEW: A queue to buffer video packets between the reader and writer
        self.video_queue = Queue(maxsize=20)
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
        self._audio_buffer = bytearray()

    async def start(self):
        self.currentAction = "FFMpeg Starting"

        if self.mode == "hls":
            os.makedirs(self.outputDirectory, exist_ok=True)
            if self.removeFilesInOutputDirectory:
                for f in os.listdir(self.outputDirectory):
                    os.remove(os.path.join(self.outputDirectory, f))

        cmd = [
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
        pass_fds = ()

        if self.includeAudio:
            self.audio_r, self.audio_w = os.pipe()
            pass_fds = (self.audio_r,)
            cmd += [
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
                "32k",
            ]
        else:
            cmd += ["-map", "0:v:0", "-c:v", "copy"]

        if self.mode == "hls":
            cmd += [
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
        else:
            cmd += ["-f", "mpegts", "pipe:1"]

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
            # MODIFIED: Start two concurrent tasks and group them
            self.stream_task = asyncio.gather(
                self._stream_to_ffmpeg(),  # The producer
                self._write_to_pipe(),  # The consumer
            )

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

    # NEW: The consumer task. This is the ONLY place that writes to the pipe.
    async def _write_to_pipe(self):
        while self.running:
            try:
                packet = await self.video_queue.get()
                if packet is None:  # Sentinel value to stop the loop
                    break
                self.streamProcess.stdin.write(packet)
                await self.streamProcess.stdin.drain()
            except asyncio.CancelledError:
                break
        if self.streamProcess.stdin and not self.streamProcess.stdin.is_closing():
            self.streamProcess.stdin.close()

    # MODIFIED: The producer task. It only reads from the camera and puts data on the queue.
    async def _stream_to_ffmpeg(self):
        loop = asyncio.get_running_loop()
        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(self.window_size)
        self.currentAction = "Streaming"
        _ts_buffer = bytearray()

        try:
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

                    if self.includeAudio and resp.audioPayload:
                        self._audio_buffer += resp.audioPayload
                        while len(self._audio_buffer) >= 160:
                            frame = self._audio_buffer[:160]
                            self._audio_buffer = self._audio_buffer[160:]
                            try:
                                await loop.run_in_executor(
                                    None, os.write, self.audio_w, frame
                                )
                            except OSError:
                                break

                    _ts_buffer += resp.plaintext
                    while len(_ts_buffer) >= 188 and _ts_buffer[0] != 0x47:
                        pos = _ts_buffer.find(b"\x47", 1)
                        if pos == -1:
                            _ts_buffer.clear()
                            break
                        _ts_buffer = _ts_buffer[pos:]

                    while len(_ts_buffer) >= 188:
                        packet = _ts_buffer[:188]
                        _ts_buffer = _ts_buffer[188:]
                        await self.video_queue.put(
                            packet
                        )  # Put video packet on the queue
        except asyncio.CancelledError:
            pass
        finally:
            await self.video_queue.put(None)  # Signal the writer to stop

    async def stop(self):
        self.currentAction = "Stopping stream"
        self.running = False
        if self.stream_task:
            self.stream_task.cancel()
            try:
                await self.stream_task
            except asyncio.CancelledError:
                pass

        if self.audio_w:
            os.close(self.audio_w)
        if self.audio_r:
            os.close(self.audio_r)

        if self.streamProcess and self.streamProcess.returncode is None:
            self.streamProcess.terminate()
            await self.streamProcess.wait()
