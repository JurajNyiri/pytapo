import json
import os
import asyncio
import subprocess
from asyncio import Queue

HLS_TIME = 1
HLS_LIST_SIZE = 3
HLS_FLAGS = "delete_segments+append_list"
ANALYZE_DURATION = 0
FFMPEG_LOG_LEVEL = "debug"


class Streamer:
    FRESH_RECORDING_TIME_SECONDS = 60
    CHUNK_SAVE_INTERVAL = 150

    def __init__(
        self,
        tapo,
        callbackFunction,
        outputDirectory="./",
        window_size=None,
        fileName=None,
    ):
        self.currentAction = "Idle"
        self.callbackFunction = callbackFunction
        self.tapo = tapo
        self.fileName = fileName or "stream_output.ts"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 200
        self.running = False

    async def start_hls(self):
        """Starts HLS stream using ffmpeg with video and audio through pipes."""
        self.currentAction = "FFMpeg Starting"
        os.makedirs(self.outputDirectory, exist_ok=True)

        # Create OS pipes for video and audio
        self.video_r, self.video_w = os.pipe()
        self.audio_r, self.audio_w = os.pipe()

        # Set pipes to non-blocking
        os.set_blocking(self.video_w, False)
        os.set_blocking(self.audio_w, False)

        hls_cmd = [
            "ffmpeg",
            "-loglevel",
            "debug",
            "-probesize",
            "32",
            "-analyzeduration",
            f"{ANALYZE_DURATION}",
            "-f",
            "mpegts",
            "-i",
            f"/dev/fd/{self.video_r}",
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
            "-f",
            "hls",
            "-hls_time",
            f"{HLS_TIME}",
            "-hls_list_size",
            f"{HLS_LIST_SIZE}",
            "-hls_flags",
            HLS_FLAGS,
            os.path.join(self.outputDirectory, "video.m3u8"),
        ]

        self.hlsProcess = await asyncio.create_subprocess_exec(
            *hls_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(self.video_r, self.audio_r),
        )

        asyncio.create_task(self._print_ffmpeg_logs(self.hlsProcess.stderr))
        self.running = True

        # Start streaming tasks
        self.video_queue = Queue(maxsize=100)
        self.audio_queue = Queue(maxsize=100)
        asyncio.create_task(self._pipe_writer(self.video_w, self.video_queue, "video"))
        asyncio.create_task(self._pipe_writer(self.audio_w, self.audio_queue, "audio"))
        asyncio.create_task(self._stream_to_queues())

    async def _print_ffmpeg_logs(self, stderr):
        while True:
            line = await stderr.readline()
            if not line:
                break
            print(f"FFmpeg: {line.decode().strip()}")

    async def _pipe_writer(self, pipe_fd, queue: Queue, name):
        """Writes data from queue to the pipe asynchronously."""
        while self.running:
            data = await queue.get()
            if data is None:  # Stop signal
                break
            try:
                os.write(pipe_fd, data)
            except BlockingIOError:
                print(f"Pipe {name} is full, retrying later")
                await asyncio.sleep(0.01)  # Small delay before retrying

    async def _stream_to_queues(self):
        """Streams both video and audio to ffmpeg via asyncio queues."""
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
                            "channels": [0, 1],
                            "resolutions": ["HD"],
                        },
                        "method": "get",
                    },
                }
            )

            async for resp in mediaSession.transceive(payload):
                if not self.running:
                    break
                if resp.mimetype == "video/mp2t":
                    if resp.audioPayload:
                        await self.audio_queue.put(resp.audioPayload)
                    await self.video_queue.put(resp.plaintext)

        # Stop writers
        await self.video_queue.put(None)
        await self.audio_queue.put(None)

    async def stop_hls(self):
        """Stops the HLS streaming process."""
        self.currentAction = "Stopping HLS..."
        self.running = False
        if self.hlsProcess:
            self.hlsProcess.terminate()
            await self.hlsProcess.wait()
            os.close(self.video_w)
            os.close(self.video_r)
            os.close(self.audio_w)
            os.close(self.audio_r)
        self.currentAction = "Idle"
        self.callbackFunction({"currentAction": self.currentAction})
