import asyncio
import aiofiles
import json
import os
import hashlib
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
                    self.outputDirectory + str(dateStart) + "-" + dateEnd + ".mp4"
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
                    payload = {
                        "type": "request",
                        "seq": 1,
                        "params": {
                            "playback": {
                                "client_id": self.tapo.getUserID(),
                                "channels": [0, 1],
                                "scale": "1/1",
                                "start_time": str(self.startTime),
                                "end_time": str(self.endTime),
                                "event_type": [1, 2],
                            },
                            "method": "get",
                        },
                    }

                    payload = json.dumps(payload)
                    dataChunks = 0
                    if retry:
                        currentAction = "Retrying"
                    else:
                        currentAction = "Downloading"
                    downloadedFull = False
                    stream = mediaSession.transceive(payload)
                    while True:
                        try:
                            if self.stall_timeout and self.stall_timeout > 0:
                                resp = await asyncio.wait_for(
                                    stream.__anext__(), timeout=self.stall_timeout
                                )
                            else:
                                resp = await stream.__anext__()
                        except StopAsyncIteration:
                            self.tapo.debugLog("Received end of stream.")
                            break
                        except asyncio.TimeoutError:
                            # Camera stopped responding mid-download; break out so we can retry.
                            self.tapo.debugLog(
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
                            detectedLength = convert.getLength()
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
                                downloadedFull = True
                                currentAction = "Converting"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                                await convert.save(fileName, segmentLength)
                                downloading = False
                                break
                        # in case a finished stream notification is caught, save the chunks as is
                        elif resp.mimetype == "application/json":
                            try:
                                json_data = json.loads(resp.plaintext.decode())

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
                                    self.tapo.debugLog(
                                        "Received json notification about finished stream."
                                    )
                                    downloadedFull = True
                                    currentAction = "Converting"
                                    yield {
                                        "currentAction": currentAction,
                                        "fileName": fileName,
                                        "progress": 0,
                                        "total": 0,
                                    }
                                    await convert.save(fileName, convert.getLength())
                                    downloading = False
                                    break
                            except JSONDecodeError:
                                self.tapo.debugLog(
                                    "Unable to parse JSON sent from device"
                                )
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
                            detectedLength = convert.getLength()
                            if (
                                detectedLength >= segmentLength - 5
                            ):  # workaround for weird cases where the recording is a bit shorter than reported
                                downloadedFull = True
                                currentAction = "Converting [shorter]"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                                await convert.save(fileName, segmentLength)
                            else:
                                currentAction = "Giving up"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                            downloading = False
