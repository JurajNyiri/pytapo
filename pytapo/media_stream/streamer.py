from .convert import Convert

import json
import os
import aiofiles

import asyncio


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
                            "audio": ["default"],
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
            print(path)
            await f.write(self.buffer)
        self.buffer.clear()  # Clear buffer after writing
