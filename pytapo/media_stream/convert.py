import logging
import io
import subprocess
import shutil
import os
import datetime
import tempfile
import time
import aiofiles
from rtp import PayloadType

logger = logging.getLogger(__name__)
logging.getLogger("libav").setLevel(logging.ERROR)


class Convert:
    def __init__(self):
        missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
        if missing:
            raise RuntimeError(
                "Required executable(s) not found on PATH: "
                + ", ".join(missing)
                + ". Install FFmpeg with both ffmpeg and ffprobe available on PATH."
            )
        self.stream = None
        self.writer = io.BytesIO()
        self.audioWriter = io.BytesIO()
        self.known_lengths = {}
        self.addedChunks = 0
        self.lengthLastCalculatedAtChunk = 0
        self.audio_payload_type = PayloadType.PCMA
        self.audio_sample_rate = 8000
        self._last_length_calc_time = None
        self._cached_bytes_per_second = None
        self._min_time_between_ffprobe = 5.0  # seconds

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
        tmp_name = None
        self._last_length_calc_time = time.time()
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_name = tmp.name
                tmp.write(self.writer.getvalue())
            # Closing the file flushes buffered data before ffprobe reads it.
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "fatal",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    tmp_name,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            detectedLength = float(result.stdout)
            self.known_lengths[self.addedChunks] = detectedLength
            self.lengthLastCalculatedAtChunk = self.addedChunks
            # Cache the bytes-per-second ratio so cheap estimates can be
            # used between ffprobe calls instead of spawning a subprocess
            # for every progress update.
            if detectedLength and detectedLength > 0:
                self._cached_bytes_per_second = (
                    len(self.writer.getvalue()) / detectedLength
                )
        except Exception as e:
            logger.debug("Could not calculate length from stream: %s", e)
        finally:
            if tmp_name is not None:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
        return detectedLength

    def _should_recalculate_length(self):
        """Decide whether to pay the cost of an ffprobe subprocess call."""
        if self._last_length_calc_time is None:
            return True
        # Do not run ffprobe more often than _min_time_between_ffprobe seconds.
        # This prevents the download loop from spawning hundreds of ffprobe
        # processes on fast streams with small chunks.
        if time.time() - self._last_length_calc_time < self._min_time_between_ffprobe:
            return False
        if not self.known_lengths:
            # ffprobe has failed so far; keep retrying, but only at the
            # throttled rate above.
            return True
        if (
            self.addedChunks
            > self.lengthLastCalculatedAtChunk
            + self.getRefreshIntervalForLengthEstimate()
        ):
            return True
        return False

    # returns length of video, can return an estimate which is usually very close
    def getLength(self, exact=False):
        # Finalization must probe the complete buffer and must not fall back to
        # a progress estimate if that probe fails.
        if exact:
            return self.calculateLength()
        lastKnownChunk = 0
        lastKnownLength = 0
        has_known_lengths = bool(self.known_lengths)
        if has_known_lengths:
            lastKnownChunk = list(self.known_lengths)[-1]
            lastKnownLength = self.known_lengths[lastKnownChunk]
        if self._should_recalculate_length() or (
            has_known_lengths and lastKnownLength == 0
        ):
            calculatedLength = self.calculateLength()
            if calculatedLength is not False:
                return calculatedLength
            elif has_known_lengths:
                bytesPerChunk = lastKnownChunk / lastKnownLength
                return self.addedChunks / bytesPerChunk
        else:
            # Prefer a bytes-per-second estimate once a ratio has been cached,
            # as it avoids the chunk-count assumption when bitrate changes.
            if self._cached_bytes_per_second:
                return len(self.writer.getvalue()) / self._cached_bytes_per_second
            if has_known_lengths:
                bytesPerChunk = lastKnownChunk / lastKnownLength
                return self.addedChunks / bytesPerChunk
        return False

    def write(self, data: bytes, audioData: bytes, audioPayloadType=None, audioSampleRate=None):
        self.addedChunks += 1
        self._set_audio_properties(audioPayloadType, audioSampleRate)
        return self.writer.write(data) and self.audioWriter.write(audioData)
