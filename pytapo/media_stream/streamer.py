from .convert import Convert

import json
import os
import aiofiles
import asyncio
import subprocess


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
        self.fileName = fileName or "stream_output.ts"
        self.outputDirectory = outputDirectory
        self.window_size = int(window_size) if window_size else 200
        self.buffer = bytearray()  # Local buffer for storing retrieved data
        self.audioProcess = None
        self.videoProcess = None
        self.hls_task = None
        self.running = False

    async def start_hls(self):
        """Starts HLS stream using ffmpeg with proper codecs."""
        self.currentAction = "FFMpeg Starting"
        os.makedirs(self.outputDirectory, exist_ok=True)
        output_path = os.path.join(self.outputDirectory, "stream.m3u8")

        # Clean up old HLS files
        for f in os.listdir(self.outputDirectory):
            os.remove(os.path.join(self.outputDirectory, f))

        audio_cmd = [
            "ffmpeg",
            "-loglevel",
            "debug",
            "-f",
            "alaw",  # Tell FFmpeg that input is raw a-law audio
            "-ar",
            "8000",
            "-i",
            "pipe:0",  # Use another pipe for audio
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "hls",
            "-hls_time",
            "5",
            "-hls_list_size",
            "10",
            "-hls_flags",
            "delete_segments",
            os.path.join(self.outputDirectory, "audio.m3u8"),
        ]

        video_cmd = [
            "ffmpeg",
            "-bsf:v",
            "h264_mp4toannexb",
            "-loglevel",
            "debug",
            "-probesize",
            "32",
            "-f",
            "mpegts",
            "-i",
            "pipe:0",
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            "5",
            "-hls_list_size",
            "10",
            "-hls_flags",
            "delete_segments",
            os.path.join(self.outputDirectory, "video.m3u8"),
        ]

        self.audioProcess = await asyncio.create_subprocess_exec(
            *audio_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.videoProcess = await asyncio.create_subprocess_exec(
            *video_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.currentAction = "FFMpeg Running"

        self.running = True

        if self.hls_task is None or self.hls_task.done():
            self.hls_task = asyncio.create_task(self._stream_to_ffmpeg())

        print("HLS stream started.")

    async def _stream_to_ffmpeg(self):
        """Handles mediaSession streaming in the background."""
        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(self.window_size)
        self.currentAction = "Stream Starting"

        async with mediaSession:
            payload = json.dumps(
                {
                    "type": "request",
                    "seq": 1,
                    "params": {
                        "preview": {
                            "audio": ["default"],  # Ensure audio is included
                            "channels": [0, 1],
                            "resolutions": ["HD"],
                        },
                        "method": "get",
                    },
                }
            )

            print(f"Starting HLS stream at: {self.outputDirectory}")

            async def log_ffmpeg_audio():
                """Continuously print FFmpeg logs."""
                while True:
                    if self.audioProcess.stderr.at_eof():
                        break
                    line = await self.audioProcess.stderr.readline()
                    self.callbackFunction(
                        {
                            "currentAction": self.currentAction,
                            "ffmpeg_log": line.decode().strip(),
                        }
                    )

            async def log_ffmpeg_video():
                """Continuously print FFmpeg logs."""
                while True:
                    if self.videoProcess.stderr.at_eof():
                        break
                    line = await self.videoProcess.stderr.readline()
                    self.callbackFunction(
                        {
                            "currentAction": self.currentAction,
                            "ffmpeg_log": line.decode().strip(),
                        }
                    )

            asyncio.create_task(log_ffmpeg_audio())
            asyncio.create_task(log_ffmpeg_video())

            print(f"FFmpeg Audio PID: {self.audioProcess.pid}")
            print(f"FFmpeg Video PID: {self.videoProcess.pid}")

            async for resp in mediaSession.transceive(payload):
                if not self.running:
                    break
                if resp.mimetype == "video/mp2t":
                    self.currentAction = "Streaming"
                    try:
                        if len(resp.plaintext) % 188 != 0:
                            print(
                                f"Warning: Dropping incomplete TS packet ({len(resp.plaintext)} bytes)"
                            )
                            continue

                        self.videoProcess.stdin.write(resp.plaintext)

                        if resp.audioPayload:
                            self.audioProcess.stdin.write(resp.audioPayload)
                            await self.audioProcess.stdin.drain()

                        await self.videoProcess.stdin.drain()
                    except (BrokenPipeError, AttributeError):
                        self.currentAction = "FFMpeg crashed"
                        print("FFmpeg process closed unexpectedly.")
                        break

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
        if self.audioProcess:
            self.currentAction = "Stopping ffmpeg..."
            self.audioProcess.terminate()
            self.audioProcess.stdin.close()
            await self.audioProcess.wait()
            self.currentAction = "Idle"
            self.callbackFunction(
                {
                    "currentAction": self.currentAction,
                }
            )
        if self.videoProcess:
            self.currentAction = "Stopping ffmpeg..."
            self.videoProcess.terminate()
            self.videoProcess.stdin.close()
            await self.videoProcess.wait()
            self.currentAction = "Idle"
            self.callbackFunction(
                {
                    "currentAction": self.currentAction,
                }
            )
