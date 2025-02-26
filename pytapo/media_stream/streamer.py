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
        self.currentAction = "Streaming"
        self.callbackFunction = callbackFunction
        self.tapo = tapo
        self.fileName = fileName or "stream_output.ts"
        self.outputDirectory = outputDirectory
        if window_size is None:
            self.window_size = 200
        else:
            self.window_size = int(window_size)
        self.buffer = bytearray()  # Local buffer for storing retrieved data

    async def download(self):
        convert = Convert()
        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(self.window_size)
        output_path = os.path.join(self.outputDirectory, self.fileName)

        async with mediaSession:
            payload = json.dumps(
                {
                    "type": "request",
                    "seq": 1,
                    "params": {
                        "preview": {
                            "audio": ["default"],  # Ensure audio is included
                            "channels": [0],
                            "resolutions": ["HD"],
                        },
                        "method": "get",
                    },
                }
            )

            dataChunks = 0
            async for resp in mediaSession.transceive(payload):
                if resp.mimetype == "video/mp2t":
                    dataChunks += 1
                    convert.write(resp.plaintext, resp.audioPayload)

                    # Store the received data in buffer
                    self.buffer.extend(resp.plaintext)
                    if resp.audioPayload:
                        self.buffer.extend(resp.audioPayload)

                    # Save to file for debugging purposes
                    if dataChunks % self.CHUNK_SAVE_INTERVAL == 0:
                        await self.save_to_file(output_path)

                    self.callbackFunction({"currentAction": self.currentAction})

                    await asyncio.sleep(0.1)  # Prevent tight loop

    async def save_to_file(self, path):
        """Appends buffered data to a file and clears the buffer."""
        async with aiofiles.open(path, "ab") as f:
            print(f"Saving chunk to {path}")
            await f.write(self.buffer)
        self.buffer.clear()  # Clear buffer after writing

    async def start_hls(self):
        """Starts HLS stream using ffmpeg with proper codecs."""
        os.makedirs(self.outputDirectory, exist_ok=True)
        output_path = os.path.join(self.outputDirectory, "stream.m3u8")

        # Clean up old HLS files
        for f in os.listdir(self.outputDirectory):
            os.remove(os.path.join(self.outputDirectory, f))

        cmd = [
            "ffmpeg",
            "-bsf:v",
            "h264_mp4toannexb",
            "-loglevel",
            "debug",  # Verbose logs
            "-probesize",
            "32",  # Reduce probe size
            "-f",
            "mpegts",  # Assume input is H.264 to prevent unnecessary analysis
            "-i",
            "pipe:0",  # Read from stdin
            "-map",
            "0:v:0",  # Select first video stream
            "-c:v",
            "copy",  # Copy video without re-encoding
            "-f",
            "hls",
            "-hls_time",
            "5",  # Shorter segment duration for lower latency
            "-hls_list_size",
            "10",  # Maintain buffer for smooth playback
            "-hls_flags",
            "delete_segments",  # Remove old segments
            output_path,
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await asyncio.sleep(1)  # Give FFmpeg time to initialize

        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(self.window_size)

        async with mediaSession:
            payload = json.dumps(
                {
                    "type": "request",
                    "seq": 1,
                    "params": {
                        "preview": {
                            "audio": ["default"],  # Ensure audio is included
                            "channels": [0],
                            "resolutions": ["HD"],
                        },
                        "method": "get",
                    },
                }
            )
            print(f"Starting HLS stream at: {self.outputDirectory}")

            async def log_ffmpeg():
                """Continuously print FFmpeg logs."""
                while True:
                    if self.process.stderr.at_eof():
                        break
                    line = await self.process.stderr.readline()
                    self.callbackFunction(
                        {
                            "currentAction": self.currentAction,
                            "ffmpeg_log": line.decode().strip(),
                        }
                    )

            asyncio.create_task(log_ffmpeg())  # Run as a background task

            print(f"FFmpeg PID: {self.process.pid}")

            async for resp in mediaSession.transceive(payload):
                if resp.mimetype == "video/mp2t":
                    try:
                        # Ensure full TS packets before writing
                        if len(resp.plaintext) % 188 != 0:
                            print(
                                f"Warning: Dropping incomplete TS packet ({len(resp.plaintext)} bytes)"
                            )
                            continue  # Skip writing incomplete packets

                        self.process.stdin.write(resp.plaintext)
                        if resp.audioPayload:
                            self.process.stdin.write(resp.audioPayload)
                        await self.process.stdin.drain()  # Ensure data is flushed asynchronously
                    except BrokenPipeError:
                        print("FFmpeg process closed unexpectedly.")
                        break  # Stop the loop if ffmpeg exits

            stderr_output = self.process.stderr.read().decode()
            print(stderr_output)  # Print FFmpeg errors
