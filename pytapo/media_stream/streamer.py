from .convert import Convert

import json
import os
import aiofiles
import asyncio
import subprocess


class Streamer:
    FRESH_RECORDING_TIME_SECONDS = 60
    CHUNK_SAVE_INTERVAL = 150  # Save after 10 chunks

    def __init__(self, tapo, outputDirectory="./", window_size=None, fileName=None):
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

                    yield {"currentAction": "Streaming"}

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
            "-loglevel",
            "debug",  # Verbose logs
            "-f",
            "mpegts",  # Force input format as MPEG-TS
            "-probesize",
            "8M",  # Optimize probing for faster stream start
            "-analyzeduration",
            "2M",  # Reduce latency while keeping stream stability
            "-i",
            "pipe:0",  # Read from stdin
            "-c:v",
            "copy",  # Copy video without re-encoding (Tapo uses H.264)
            "-c:a",
            "aac",  # Convert audio if needed
            "-b:a",
            "64k",  # Set AAC bitrate
            "-f",
            "hls",
            "-hls_time",
            "2",  # Shorter segment duration for lower latency
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

        convert = Convert()
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
                    print("[FFmpeg]", line.decode().strip())

            asyncio.create_task(log_ffmpeg())  # Run as a background task

            print(f"FFmpeg PID: {self.process.pid}")

            async for resp in mediaSession.transceive(payload):
                yield {"currentAction": "Streaming"}
                if resp.mimetype == "video/mp2t":
                    try:
                        # Ensure full TS packets before writing
                        if len(resp.plaintext) % 188 != 0:
                            print(
                                f"Warning: Dropping incomplete TS packet ({len(resp.plaintext)} bytes)"
                            )
                            continue  # Skip writing incomplete packets

                        self.process.stdin.write(resp.plaintext)
                        await self.process.stdin.drain()  # Ensure data is flushed asynchronously
                    except BrokenPipeError:
                        print("FFmpeg process closed unexpectedly.")
                        break  # Stop the loop if ffmpeg exits

            stderr_output = self.process.stderr.read().decode()
            print(stderr_output)  # Print FFmpeg errors
