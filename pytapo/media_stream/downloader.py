import asyncio
import aiofiles
import json
import os
import hashlib
import math
import time
from datetime import datetime
from json import JSONDecodeError
from pytapo import Tapo
from .convert import Convert
from ._utils import StreamType


class Downloader:
    FRESH_RECORDING_TIME_SECONDS = 60
    STALL_TIMEOUT_SECONDS = 120

    def __init__(
        self,
        tapo: Tapo,
        startTime: int,
        endTime: int,
        timeCorrection: int,
        outputDirectory="./",
        padding=None,
        overwriteFiles=None,
        window_size=None,  # affects download speed, with higher values camera sometimes stops sending data
        fileName=None,
        stall_timeout=None,
        progressInterval=1.0,  # minimum seconds between progress updates
        output="mp4",  # "mp4" (remux with ffmpeg) or "ts" (raw MPEG-TS as sent by the camera)
        method="download",  # "download" (fast, what the Tapo app uses) or "playback" (realtime)
    ):
        self.tapo = tapo
        self.startTime = startTime
        self.endTime = endTime
        self.padding = padding
        self.fileName = fileName
        self.timeCorrection = timeCorrection
        if padding is None:
            self.padding = 5
        else:
            self.padding = int(padding)

        self.outputDirectory = outputDirectory
        self.overwriteFiles = overwriteFiles
        if window_size is None:
            self.window_size = 200
        else:
            self.window_size = int(window_size)
        self.audio_sample_rate = None
        self.stall_timeout = (
            self.STALL_TIMEOUT_SECONDS if stall_timeout is None else int(stall_timeout)
        )
        self.progressInterval = float(progressInterval)
        self._last_progress_time = 0.0
        if output not in ("mp4", "ts"):
            raise ValueError("output must be 'mp4' or 'ts'")
        self.output = output
        if method not in ("download", "playback"):
            raise ValueError("method must be 'download' or 'playback'")
        self.method = method

    @property
    def _saveMethod(self):
        return "raw" if self.output == "ts" else "ffmpeg"
    def _buildRequest(self):
        """The stream request for [startTime, endTime].

        "download" is what the Tapo app sends when you tap download on a recording:
        the camera delivers the clip as fast as the link allows (about 10x realtime
        on Wi-Fi), keeps the full frame rate and the audio, and stops by itself at
        end_time with a stream_status "finished" notification. "playback" is the
        player request: paced at 1x realtime and it does not stop at end_time, the
        length is bounded by measuring the received video instead.
        """
        if self.method == "download":
            params = {
                "download": {
                    "client_id": self.tapo.getUserID(),
                    "channels": [0],
                    "media_type": 0,
                    "start_time": str(self.startTime),
                    "end_time": str(self.endTime),
                    "player_id": self.tapo.playerID,
                },
                "method": "get",
            }
        else:
            params = {
                "playback": {
                    "client_id": self.tapo.getUserID(),
                    "channels": [0, 1],
                    "scale": "1/1",
                    "start_time": str(self.startTime),
                    "end_time": str(self.endTime),
                    "event_type": [1, 2],
                },
                "method": "get",
            }
        return {"type": "request", "seq": 1, "params": params}

    async def md5(self, fileName):
        if os.path.isfile(fileName):
            async with aiofiles.open(fileName, "rb") as file:
                contents = await file.read()
            return hashlib.md5(contents).hexdigest()
        return False

    async def _get_audio_sample_rate(self):
        try:
            loop = asyncio.get_event_loop()
            audio_config = await loop.run_in_executor(None, self.tapo.getAudioConfig)
            rate = (
                audio_config.get("audio_config", {})
                .get("microphone", {})
                .get("sampling_rate")
            )
            if rate is None:
                return None
            return int(rate) * 1000
        except Exception:
            return None

    async def downloadFile(self, callbackFunc=None):
        if callbackFunc is not None:
            callbackFunc("Starting download")
        async for status in self.download():
            if callbackFunc is not None:
                callbackFunc(status)
            pass
        if callbackFunc is not None:
            callbackFunc("Finished download")

        md5Hash = await self.md5(status["fileName"])

        status["md5"] = "" if md5Hash is False else md5Hash

        return status

    async def download(self, retry=False):
        downloading = True
        while downloading:
            # todo: add a way to not download recent videos to prevent videos in progress
            dateStart = datetime.utcfromtimestamp(int(self.startTime)).strftime(
                "%Y-%m-%d %H_%M_%S"
            )
            dateEnd = datetime.utcfromtimestamp(int(self.endTime)).strftime(
                "%Y-%m-%d %H_%M_%S"
            )
            segmentLength = self.endTime - self.startTime
            if self.fileName is None:
                fileName = (
                    self.outputDirectory + str(dateStart) + "-" + dateEnd + "." + self.output
                )
            else:
                fileName = self.outputDirectory + self.fileName
            if (
                datetime.now().timestamp()
                - self.FRESH_RECORDING_TIME_SECONDS
                - self.timeCorrection
                < self.endTime
            ):
                currentAction = "Recording in progress"
                yield {
                    "currentAction": currentAction,
                    "fileName": fileName,
                    "progress": 0,
                    "total": 0,
                }
                downloading = False
            elif os.path.isfile(fileName):
                currentAction = "Skipping"
                yield {
                    "currentAction": currentAction,
                    "fileName": fileName,
                    "progress": 0,
                    "total": 0,
                }
                downloading = False
            else:
                convert = Convert()
                if self.audio_sample_rate is None:
                    self.audio_sample_rate = await self._get_audio_sample_rate()
                mediaSession = self.tapo.getMediaSession(StreamType.Download)
                if retry:
                    mediaSession.set_window_size(50)
                else:
                    mediaSession.set_window_size(self.window_size)
                async with mediaSession:
                    payload = json.dumps(self._buildRequest())
                    unsupported = False
                    dataChunks = 0
                    if retry:
                        currentAction = "Retrying"
                    else:
                        currentAction = "Downloading"
                    downloadedFull = False
                    detectedLength = 0
                    stream = mediaSession.transceive(payload)
                    try:
                        while True:
                            try:
                                if self.stall_timeout and self.stall_timeout > 0:
                                    resp = await asyncio.wait_for(
                                        stream.__anext__(), timeout=self.stall_timeout
                                    )
                                else:
                                    resp = await stream.__anext__()
                            except StopAsyncIteration:
                                self.tapo.logger.debugLog("Received end of stream.")
                                break
                            except asyncio.TimeoutError:
                                # Camera stopped responding mid-download; break out so we can retry.
                                self.tapo.logger.debugLog(
                                    "Timed out waiting for recording data, retrying."
                                )
                                break
                            if resp.mimetype == "video/mp2t":
                                dataChunks += 1
                                convert.write(
                                    resp.plaintext,
                                    resp.audioPayload,
                                    resp.audioPayloadType,
                                    self.audio_sample_rate,
                                )
                                now = time.time()
                                if now - self._last_progress_time >= self.progressInterval:
                                    detectedLength = convert.getLength()
                                    self._last_progress_time = now
                                    if detectedLength is False:
                                        yield {
                                            "currentAction": currentAction,
                                            "fileName": fileName,
                                            "progress": 0,
                                            "total": segmentLength,
                                        }
                                        detectedLength = 0
                                    else:
                                        yield {
                                            "currentAction": currentAction,
                                            "fileName": fileName,
                                            "progress": detectedLength,
                                            "total": segmentLength,
                                        }
                                if (detectedLength > segmentLength + self.padding) or (
                                    retry
                                    and detectedLength
                                    >= segmentLength  # fix for the latest latest recording
                                ):
                                    if detectedLength == 0:
                                        detectedLength = convert.getLength()
                                        if detectedLength is False:
                                            detectedLength = 0
                                    downloadedFull = True
                                    currentAction = "Converting"
                                    yield {
                                        "currentAction": currentAction,
                                        "fileName": fileName,
                                        "progress": 0,
                                        "total": 0,
                                    }
                                    await convert.save(fileName, segmentLength, self._saveMethod)
                                    downloading = False
                                    break
                            # in case a finished stream notification is caught, save the chunks as is
                            elif resp.mimetype == "application/json":
                                try:
                                    json_data = json.loads(resp.plaintext.decode())

                                    if (
                                        self.method == "download"
                                        and json_data.get("type") == "response"
                                        and (json_data.get("params") or {}).get(
                                            "error_code", 0
                                        )
                                        not in (0, None)
                                    ):
                                        # this firmware does not know the download
                                        # request: do it the old way
                                        self.tapo.logger.debugLog(
                                            "Camera refused the download request "
                                            f"({json_data['params']['error_code']}), "
                                            "falling back to playback."
                                        )
                                        unsupported = True
                                        break
                                    if (
                                        "type" in json_data
                                        and json_data["type"] == "notification"
                                        and "params" in json_data
                                        and "event_type" in json_data["params"]
                                        and json_data["params"]["event_type"]
                                        == "stream_status"
                                        and "status" in json_data["params"]
                                        and json_data["params"]["status"] == "finished"
                                    ):
                                        self.tapo.logger.debugLog(
                                            "Received json notification about finished stream."
                                        )
                                        detectedLength = convert.getLength(exact=True)
                                        if (
                                            not math.isfinite(detectedLength)
                                            or detectedLength <= 0
                                        ):
                                            self.tapo.logger.debugLog(
                                                "Could not determine finished recording duration."
                                            )
                                            break
                                        downloadedFull = True
                                        currentAction = "Converting"
                                        yield {
                                            "currentAction": currentAction,
                                            "fileName": fileName,
                                            "progress": 0,
                                            "total": 0,
                                        }
                                        await convert.save(fileName, detectedLength, self._saveMethod)
                                        downloading = False
                                        break
                                except JSONDecodeError:
                                    self.tapo.logger.debugLog(
                                        "Unable to parse JSON sent from device"
                                    )
                    finally:
                        if stream is not None:
                            try:
                                await stream.aclose()
                            except (AttributeError, RuntimeError, StopAsyncIteration):
                                pass
                    if unsupported:
                        self.method = "playback"
                        continue
                    if downloading:
                        # Handle case where camera randomly stopped respoding
                        if not downloadedFull and not retry:
                            currentAction = "Retrying"
                            yield {
                                "currentAction": currentAction,
                                "fileName": fileName,
                                "progress": 0,
                                "total": 0,
                            }
                            retry = True
                        else:
                            detectedLength = convert.getLength(exact=True)
                            if (
                                math.isfinite(detectedLength)
                                and detectedLength > 0
                                and detectedLength >= segmentLength - 5
                            ):  # workaround for weird cases where the recording is a bit shorter than reported
                                downloadedFull = True
                                currentAction = "Converting [shorter]"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                                await convert.save(fileName, segmentLength, self._saveMethod)
                            else:
                                currentAction = "Giving up"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                            downloading = False
