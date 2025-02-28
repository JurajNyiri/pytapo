import json
import os
import asyncio
import subprocess

HLS_TIME = 1
HLS_LIST_SIZE = 3
HLS_FLAGS = "delete_segments+append_list"
ANALYZE_DURATION = 0
PROBE_SIZE = 32
FFMPEG_LOG_LEVEL = "info"


class Streamer:
    FRESH_RECORDING_TIME_SECONDS = 60
    CHUNK_SAVE_INTERVAL = 150  # Save after 10 chunks

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
        self.fileName = fileName or "stream_output.m3u8"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 200
        self.hls_task = None
        self.running = False

    async def start_hls(self):
        """Starts HLS stream using ffmpeg without writing intermediate files."""
        self.currentAction = "FFMpeg Starting"
        os.makedirs(self.outputDirectory, exist_ok=True)

        self.audio_r, self.audio_w = os.pipe()

        hls_cmd = [
            "ffmpeg",
            "-loglevel",
            f"{FFMPEG_LOG_LEVEL}",
            "-probesize",
            f"{PROBE_SIZE}",
            "-analyzeduration",
            f"{ANALYZE_DURATION}",
            "-f",
            "mpegts",
            "-i",
            "pipe:0",  # Video input from pipe
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
            "aac",  # Convert A-law audio to AAC
            "-b:a",
            "128k",  # Set audio bitrate
            "-f",
            "hls",  # Output format as HLS
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
            pass_fds=(self.audio_r,),  # Pass the read end of the pipe
        )

        asyncio.create_task(self._print_ffmpeg_logs(self.hlsProcess.stderr))

        print("FFmpeg process started")

        self.running = True
        if self.hls_task is None or self.hls_task.done():
            self.hls_task = asyncio.create_task(self._stream_to_ffmpeg())

    async def _print_ffmpeg_logs(self, stderr):
        """Reads and prints FFmpeg logs asynchronously."""
        while True:
            line = await stderr.readline()
            if not line:
                break
            print(f"FFmpeg: {line.decode().strip()}")

    async def _stream_to_ffmpeg(self):
        """Streams both video and audio to ffmpeg in memory."""
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
                    if len(resp.plaintext) % 188 != 0:
                        print(
                            f"Warning: Dropping incomplete TS packet ({len(resp.plaintext)} bytes)"
                        )
                        continue

                    if resp.audioPayload:
                        try:
                            os.write(self.audio_w, resp.audioPayload)
                        except OSError as e:
                            print(f"Error writing audio to pipe: {e}")
                            break
                    else:
                        self.hlsProcess.stdin.write(resp.plaintext)

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
