from pytapo.media_stream.convert import Convert
from pytapo import Tapo
from datetime import datetime
import json
import os


class Downloader:
    def __init__(
        self,
        tapo: Tapo,
        startTime: int,
        endTime: int,
        outputDirectory="./",
        padding=5,
        overwriteFiles=False,
    ):
        self.tapo = tapo
        self.startTime = startTime
        self.endTime = endTime
        self.padding = padding
        self.outputDirectory = outputDirectory
        self.overwriteFiles = overwriteFiles

    async def download(self, retry=False):
        downloading = True
        while downloading:
            date = datetime.utcfromtimestamp(int(self.startTime)).strftime(
                "%Y-%m-%d %H_%M_%S"
            )
            segmentLength = self.endTime - self.startTime
            fileName = self.outputDirectory + str(date) + ".mp4"
            if os.path.isfile(fileName):
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

                            yield {
                                "currentAction": currentAction,
                                "fileName": fileName,
                                "progress": convert.getLength(),
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
