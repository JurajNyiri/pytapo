import logging
import io
import subprocess
import os
import datetime
import tempfile
import aiofiles
from rtp import PayloadType

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
        self.audio_payload_type = PayloadType.PCMA
        self.audio_sample_rate = 8000

    def _get_audio_format(self):
        if self.audio_payload_type == PayloadType.PCMU:
            return "mulaw"
        return "alaw"

    def _get_audio_rate(self):
        return self.audio_sample_rate

    def _set_audio_properties(self, audio_payload_type=None, sample_rate=None):
        if audio_payload_type is not None:
            self.audio_payload_type = audio_payload_type
            # Default to 16kHz for PCMU (newer firmware), 8kHz otherwise.
            if sample_rate is None:
                self.audio_sample_rate = 16000 if audio_payload_type == PayloadType.PCMU else 8000
        if sample_rate is not None:
            self.audio_sample_rate = sample_rate

    # cuts and saves the video
    async def save(self, fileLocation, fileLength, method="ffmpeg"):
        if method == "ffmpeg":
            tempVideoFileLocation = fileLocation + ".ts"
            async with aiofiles.open(tempVideoFileLocation, "wb") as file:
                await file.write(self.writer.getvalue())
            audio_format = self._get_audio_format()
            audio_rate = self._get_audio_rate()
            tempAudioFileLocation = f"{fileLocation}.{audio_format}"
            async with aiofiles.open(tempAudioFileLocation, "wb") as file:
                await file.write(self.audioWriter.getvalue())

            cmd = 'ffmpeg -ss 00:00:00 -i "{inputVideoFile}" -f {audioFormat} -ar {audioRate} -i "{inputAudioFile}" -t {videoLength} -y -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 "{outputFile}" >{devnull} 2>&1'.format(
                inputVideoFile=tempVideoFileLocation,
                inputAudioFile=tempAudioFileLocation,
                outputFile=fileLocation,
                videoLength=str(datetime.timedelta(seconds=fileLength)),
                devnull=os.devnull,
                audioFormat=audio_format,
                audioRate=audio_rate,
            )
            os.system(cmd)

            os.remove(tempVideoFileLocation)
            os.remove(tempAudioFileLocation)
        else:
            raise Exception("Method not supported")

    # calculates ideal refresh interval for a real time estimate of downloaded data
    def getRefreshIntervalForLengthEstimate(self):
        if self.addedChunks < 100:
            return 50
        elif self.addedChunks < 1000:
            return 250
        elif self.addedChunks < 10000:
            return 5000
        else:
            return self.addedChunks / 2

    # calculates real stream length, hard on processing since it has to go through all the frames
    def calculateLength(self):
        detectedLength = False
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(self.writer.getvalue())
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "fatal",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        tmp.name,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                detectedLength = float(result.stdout)
                self.known_lengths[self.addedChunks] = detectedLength
                self.lengthLastCalculatedAtChunk = self.addedChunks
            os.unlink(tmp.name)
        except Exception as e:
            print("")
            print(e)
            print("Warning: Could not calculate length from stream.")
            pass
        return detectedLength

    # returns length of video, can return an estimate which is usually very close
    def getLength(self, exact=False):
        if bool(self.known_lengths) is True:
            lastKnownChunk = list(self.known_lengths)[-1]
            lastKnownLength = self.known_lengths[lastKnownChunk]
        if (
            exact
            or not self.known_lengths
            or self.addedChunks
            > self.lengthLastCalculatedAtChunk
            + self.getRefreshIntervalForLengthEstimate()
            or lastKnownLength == 0
        ):
            calculatedLength = self.calculateLength()
            if calculatedLength is not False:
                return calculatedLength
            else:
                if bool(self.known_lengths) is True:
                    bytesPerChunk = lastKnownChunk / lastKnownLength
                    return self.addedChunks / bytesPerChunk
        else:
            bytesPerChunk = lastKnownChunk / lastKnownLength
            return self.addedChunks / bytesPerChunk
        return False

    def write(self, data: bytes, audioData: bytes, audioPayloadType=None, audioSampleRate=None):
        self.addedChunks += 1
        self._set_audio_properties(audioPayloadType, audioSampleRate)
        return self.writer.write(data) and self.audioWriter.write(audioData)
