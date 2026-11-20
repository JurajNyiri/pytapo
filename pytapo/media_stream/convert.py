import asyncio
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


async def _wait_ignoring_cancel(future):
    """Wait until future is done even if the calling task is cancelled meanwhile.

    Returns True if a cancellation was received while waiting.
    """
    cancelled = False
    while not future.done():
        try:
            await asyncio.shield(future)
        except asyncio.CancelledError:
            cancelled = True
    return cancelled


async def _cleanup(func, *args):
    """Run a blocking cleanup in a thread and wait for it to finish, even if
    the task is cancelled meanwhile; the cancellation is passed on afterwards."""
    if await _wait_ignoring_cancel(asyncio.ensure_future(asyncio.to_thread(func, *args))):
        raise asyncio.CancelledError


async def _to_thread_to_end(func, *args, **kwargs):
    """Run a blocking call in a thread and wait for it to finish, even if the
    task is cancelled meanwhile, so that the caller learns what it created.

    Returns (result, cancelled); the caller cleans up and passes the
    cancellation on. If the call failed, its exception is raised, or
    CancelledError if the task was cancelled meanwhile.
    """
    future = asyncio.ensure_future(asyncio.to_thread(func, *args, **kwargs))
    cancelled = await _wait_ignoring_cancel(future)
    if cancelled and future.exception() is not None:
        raise asyncio.CancelledError
    return future.result(), cancelled


async def _run_process(args, capture=False):
    """Run an executable without blocking the event loop.

    If the awaiting task is cancelled, the process is killed and reaped before
    CancelledError propagates, also when the task is cancelled again meanwhile.
    Returns (returncode, stdout or None).
    """
    start = asyncio.ensure_future(
        asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.STDOUT if capture else asyncio.subprocess.DEVNULL,
        )
    )
    process = None
    try:
        process = await asyncio.shield(start)
        stdout, _ = await process.communicate()
    except asyncio.CancelledError:
        if process is None:
            await _wait_ignoring_cancel(start)
            if start.cancelled() or start.exception() is not None:
                raise
            process = start.result()
        if process.returncode is None:
            process.kill()
        await _wait_ignoring_cancel(asyncio.ensure_future(process.wait()))
        raise
    return process.returncode, stdout


def _write_temporary_file(data):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    try:
        # Closing the file flushes buffered data before ffprobe reads it.
        with tmp:
            tmp.write(data)
    except BaseException:
        _remove_file(tmp.name)
        raise
    return tmp.name


def _remove_file(name):
    try:
        os.unlink(name)
    except OSError:
        pass


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
        if method == "raw":
            # the MPEG-TS exactly as the camera sent it (H.264 + G.711 audio), no ffmpeg
            async with aiofiles.open(fileLocation, "wb") as file:
                await file.write(self.writer.getvalue())
            return
        if method == "ffmpeg":
            # Keep relative filenames from being interpreted as FFmpeg options or URLs.
            fileLocation = os.path.abspath(fileLocation)
            audio_format = self._get_audio_format()
            audio_rate = self._get_audio_rate()
            temporaryDirectory, cancelled = await _to_thread_to_end(
                tempfile.mkdtemp, prefix=".pytapo-", dir=os.path.dirname(fileLocation)
            )
            try:
                if cancelled:
                    raise asyncio.CancelledError
                tempVideoFileLocation = os.path.join(temporaryDirectory, "video.ts")
                tempAudioFileLocation = os.path.join(
                    temporaryDirectory, "audio." + audio_format
                )
                async with aiofiles.open(tempVideoFileLocation, "wb") as file:
                    await file.write(self.writer.getvalue())
                async with aiofiles.open(tempAudioFileLocation, "wb") as file:
                    await file.write(self.audioWriter.getvalue())

                args = (
                    [
                        "ffmpeg",
                        "-ss",
                        "00:00:00",
                        "-f",
                        "mpegts",
                        "-protocol_whitelist",
                        "file",
                        "-i",
                        tempVideoFileLocation,
                        "-f",
                        audio_format,
                        "-ar",
                        str(audio_rate),
                        "-protocol_whitelist",
                        "file",
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
                        "0:v",
                        "-map",
                        "1:a:0",
                        fileLocation,
                    ]
                )
                try:
                    returncode, _ = await _run_process(args)
                except asyncio.CancelledError:
                    # ffmpeg was killed and may have left an incomplete file,
                    # which the downloader would take as done next time.
                    await _cleanup(_remove_file, fileLocation)
                    raise
                if returncode != 0:
                    raise subprocess.CalledProcessError(returncode, args)
            finally:
                await _cleanup(shutil.rmtree, temporaryDirectory, True)
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

    # The length can be determined blocking (calculateLength/getLength, kept
    # for backward compatibility) or without blocking the event loop
    # (calculateLengthAsync/getLengthAsync). The helpers below hold the logic
    # both variants share, so they only differ in how ffprobe is run.

    @staticmethod
    def _ffprobe_args(fileName):
        return [
            "ffprobe",
            "-v",
            "fatal",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            "-f",
            "mpegts",
            "-protocol_whitelist",
            "file",
            fileName,
        ]

    def _store_length(self, detectedLength, data):
        """Remember a length measured by ffprobe for the buffer contents data."""
        self.known_lengths[self.addedChunks] = detectedLength
        self.lengthLastCalculatedAtChunk = self.addedChunks
        # Cache the bytes-per-second ratio so cheap estimates can be
        # used between ffprobe calls instead of spawning a subprocess
        # for every progress update.
        if detectedLength and detectedLength > 0:
            self._cached_bytes_per_second = len(data) / detectedLength

    def _needs_probe(self):
        """Whether getLength has to run ffprobe instead of estimating."""
        if self._should_recalculate_length():
            return True
        return bool(self.known_lengths) and list(self.known_lengths.values())[-1] == 0

    def _estimate(self, use_cached_ratio):
        """Length estimated from earlier measurements, or False."""
        # Prefer a bytes-per-second estimate once a ratio has been cached,
        # as it avoids the chunk-count assumption when bitrate changes.
        if use_cached_ratio and self._cached_bytes_per_second:
            return len(self.writer.getvalue()) / self._cached_bytes_per_second
        if self.known_lengths:
            lastKnownChunk = list(self.known_lengths)[-1]
            bytesPerChunk = lastKnownChunk / self.known_lengths[lastKnownChunk]
            return self.addedChunks / bytesPerChunk
        return False

    # calculates real stream length, hard on processing since it has to go through all the frames
    def calculateLength(self):
        detectedLength = False
        tmp_name = None
        self._last_length_calc_time = time.time()
        data = self.writer.getvalue()
        try:
            tmp_name = _write_temporary_file(data)
            result = subprocess.run(
                self._ffprobe_args(tmp_name),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            detectedLength = float(result.stdout)
            self._store_length(detectedLength, data)
        except Exception as e:
            logger.debug("Could not calculate length from stream: %s", e)
        finally:
            if tmp_name is not None:
                _remove_file(tmp_name)
        return detectedLength

    async def calculateLengthAsync(self):
        """calculateLength without blocking the event loop.

        On cancellation ffprobe is killed and the temporary file removed.
        """
        detectedLength = False
        tmp_name = None
        self._last_length_calc_time = time.time()
        data = self.writer.getvalue()
        try:
            tmp_name, cancelled = await _to_thread_to_end(_write_temporary_file, data)
            if cancelled:
                raise asyncio.CancelledError
            _, stdout = await _run_process(self._ffprobe_args(tmp_name), capture=True)
            detectedLength = float(stdout)
            self._store_length(detectedLength, data)
        except Exception as e:
            logger.debug("Could not calculate length from stream: %s", e)
        finally:
            if tmp_name is not None:
                await _cleanup(_remove_file, tmp_name)
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
        if self._needs_probe():
            calculatedLength = self.calculateLength()
            if calculatedLength is not False:
                return calculatedLength
            return self._estimate(use_cached_ratio=False)
        return self._estimate(use_cached_ratio=True)

    async def getLengthAsync(self, exact=False):
        """getLength without blocking the event loop."""
        if exact:
            return await self.calculateLengthAsync()
        if self._needs_probe():
            calculatedLength = await self.calculateLengthAsync()
            if calculatedLength is not False:
                return calculatedLength
            return self._estimate(use_cached_ratio=False)
        return self._estimate(use_cached_ratio=True)

    def write(self, data: bytes, audioData: bytes, audioPayloadType=None, audioSampleRate=None):
        self.addedChunks += 1
        self._set_audio_properties(audioPayloadType, audioSampleRate)
        return self.writer.write(data) and self.audioWriter.write(audioData)
