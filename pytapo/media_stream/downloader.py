import hashlib
import json
import os
from datetime import datetime

from pytapo import Tapo
from pytapo.media_stream.convert import Convert


class Downloader:
    FRESH_RECORDING_TIME_SECONDS = 60

    def __init__(
        self,
        tapo: Tapo,
        startTime: int,
        endTime: int,
        outputDirectory="./",
        padding=5,
        overwriteFiles=None,
        window_size=200,  # affects download speed, with higher values camera sometimes stops sending data
        fileName=None,
    ):
        self.tapo = tapo
        self.startTime = startTime
        self.endTime = endTime
        self.padding = int(padding)
        self.fileName = fileName
        self.scriptStartTime = int(datetime.now().timestamp())
        self.outputDirectory = outputDirectory
        self.overwriteFiles = overwriteFiles
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
        callbackFunc = callbackFunc or (lambda msg: None)
        callbackFunc("Starting download")
        async for status in self.download():
            callbackFunc(status)
        callbackFunc("Finished download")
        status["md5"] = self.md5(status["fileName"]) or ""
        return status

    async def download(self):
        downloading = True
        retry = False
        while downloading:
            async for status in await self._handle_download(retry):
                yield status
            downloading = False
            retry = not retry

    async def _handle_download(self, retry=False):
        dateStart = datetime.utcfromtimestamp(int(self.startTime)).strftime(
            "%Y-%m-%d %H_%M_%S"
        )
        dateEnd = datetime.utcfromtimestamp(int(self.endTime)).strftime(
            "%Y-%m-%d %H_%M_%S"
        )
        segmentLength = self.endTime - self.startTime
        fileName = (
            (self.outputDirectory + str(dateStart) + "-" + dateEnd + ".mp4")
            if self.fileName is None
            else self.outputDirectory + self.fileName
        )
        convert = Convert()
        mediaSession = self.tapo.getMediaSession()
        mediaSession.set_window_size(50 if retry else self.window_size)
        async with mediaSession:
            payload = self._prepare_payload()
            dataChunks = 0
            downloadedFull = False
            async for resp in mediaSession.transceive(payload):
                if resp.mimetype == "video/mp2t":
                    dataChunks += 1
                    convert.write(resp.plaintext, resp.audioPayload)
                    detectedLength = convert.getLength() or 0
                    yield self._create_status(
                        "Retrying" if retry else "Downloading",
                        fileName,
                        detectedLength,
                        segmentLength,
                    )
                    if (detectedLength > segmentLength + self.padding) or (
                        retry and detectedLength >= segmentLength
                    ):
                        downloadedFull = True
                        yield self._create_status("Converting", fileName)
                        convert.save(fileName, segmentLength)
                        break
            if not downloadedFull and not retry:
                yield self._create_status("Retrying", fileName)
                retry = True
            elif detectedLength := convert.getLength():
                if detectedLength >= segmentLength - 5:
                    downloadedFull = True
                    yield self._create_status("Converting [shorter]", fileName)
                    convert.save(fileName, segmentLength)
                else:
                    yield self._create_status("Giving up", fileName)

    def _prepare_payload(self):
        return json.dumps(
            {
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
        )

    def _create_status(self, action, fileName, progress=0, total=0):
        return {
            "currentAction": action,
            "fileName": fileName,
            "progress": progress,
            "total": total,
        }
