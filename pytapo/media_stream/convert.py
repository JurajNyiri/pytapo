import logging
import io
import subprocess
import os
import datetime
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)
logging.getLogger("libav").setLevel(logging.ERROR)


class Convert:
    def __init__(self):
        self.stream = None
        self.writer = io.BytesIO()
        self.audioWriter = io.BytesIO()
        self.known_lengths = {}
        self.addedChunks = 0
        self.lengthLastCalculatedAtChunk = 0

    def save(self, fileLocation: str, fileLength: int, method: str = "ffmpeg") -> None:
        if method == "ffmpeg":
            tempVideoFileLocation = f"{fileLocation}.ts"
            with open(tempVideoFileLocation, "wb") as file:
                file.write(self.writer.getvalue())
            tempAudioFileLocation = f"{fileLocation}.alaw"
            with open(tempAudioFileLocation, "wb") as file:
                file.write(self.audioWriter.getvalue())

            cmd = [
                "ffmpeg",
                "-ss",
                "00:00:00",
                "-i",
                tempVideoFileLocation,
                "-f",
                "alaw",
                "-ar",
                "8000",
                "-i",
                tempAudioFileLocation,
                "-t",
                str(datetime.timedelta(seconds=fileLength)),
                "-y",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                fileLocation,
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.remove(tempVideoFileLocation)
            os.remove(tempAudioFileLocation)
        else:
            raise ValueError("Method not supported")

    def getRefreshIntervalForLengthEstimate(self) -> int:
        if self.addedChunks < 100:
            return 50
        elif self.addedChunks < 1000:
            return 250
        elif self.addedChunks < 10000:
            return 5000
        else:
            return self.addedChunks // 2

    def calculateLength(self) -> Optional[float]:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(self.writer.getvalue())
            tmp.flush()

            cmd = [
                "ffprobe",
                "-v",
                "fatal",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                tmp.name,
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                detected_length = float(result.stdout)
                self.known_lengths[self.addedChunks] = detected_length
                self.lengthLastCalculatedAtChunk = self.addedChunks
                return detected_length
            else:
                logger.error("Could not calculate length from stream.")
                return None

    def getLength(self, exact=False) -> Optional[float]:
        if bool(self.known_lengths):
            last_known_chunk = list(self.known_lengths)[-1]
            last_known_length = self.known_lengths[last_known_chunk]
        if (
            exact
            or not self.known_lengths
            or self.addedChunks
            > self.lengthLastCalculatedAtChunk
            + self.getRefreshIntervalForLengthEstimate()
            or last_known_length == 0
        ):
            return self.calculateLength()
        bytes_per_chunk = last_known_chunk / last_known_length
        return self.addedChunks / bytes_per_chunk

    def write(self, data: bytes, audioData: bytes) -> None:
        self.addedChunks += 1
        self.writer.write(data)
        self.audioWriter.write(audioData)
