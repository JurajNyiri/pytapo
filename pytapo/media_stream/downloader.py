from pytapo.media_stream.convert import Convert
from pytapo import Tapo
from datetime import datetime

import json
import os
import hashlib


class Downloader:
    FRESH_RECORDING_TIME_SECONDS = 60

    def __init__(
        self,
        tapo: Tapo,
        startTime: int,
        endTime: int,
        outputDirectory="./",
        padding=None,
        overwriteFiles=None,
        window_size=None,  # affects download speed, with higher values camera sometimes stops sending data
        fileName=None,
    ):
        self.tapo = tapo
        self.startTime = startTime
        self.endTime = endTime
        self.padding = padding
        self.fileName = fileName
        self.scriptStartTime = int(
            datetime.now().timestamp()
        )  # keeps track of when was class initiated
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

    def md5(self, fileName):
        if os.path.isfile(fileName):
            with open(fileName, "rb") as f:
                file_hash = hashlib.md5()
                while chunk := f.read(8192):
                    file_hash.update(chunk)
            return file_hash.hexdigest()
        return False

    async def downloadFile(self, callbackFunc=None):
        if callbackFunc is not None:
            callbackFunc("Starting download")
        async for status in self.download():
            if callbackFunc is not None:
                callbackFunc(status)
            pass
        if callbackFunc is not None:
            callbackFunc("Finished download")

        md5Hash = self.md5(status["fileName"])

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
            if self.scriptStartTime - self.FRESH_RECORDING_TIME_SECONDS < self.endTime:
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
                mediaSession = self.tapo.getMediaSession()
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
                    async for resp in mediaSession.transceive(payload):
                        if resp.mimetype == "video/mp2t":
                            dataChunks += 1
                            convert.write(resp.plaintext, resp.audioPayload)
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
                                convert.save(fileName, segmentLength)
                                downloading = False
                                break
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
                                convert.save(fileName, segmentLength)
                            else:
                                currentAction = "Giving up"
                                yield {
                                    "currentAction": currentAction,
                                    "fileName": fileName,
                                    "progress": 0,
                                    "total": 0,
                                }
                            downloading = False
