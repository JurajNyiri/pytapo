from pytapo.media_stream.convert import Convert
from pytapo import Tapo
from datetime import datetime
import json


class Downloader:
    def __init__(self, tapo: Tapo, startTime: int, endTime: int, padding=5):
        self.tapo = tapo
        self.startTime = startTime
        self.endTime = endTime
        self.padding = padding

    async def download(self):
        convert = Convert()
        mediaSession = self.tapo.getMediaSession()
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
            date = datetime.utcfromtimestamp(int(self.startTime)).strftime(
                "%Y-%m-%d %H_%M_%S"
            )
            segmentLength = self.endTime - self.startTime
            print("Downloading " + date + "")
            async for resp in mediaSession.transceive(payload):
                if resp.mimetype == "video/mp2t":
                    dataChunks += 1
                    convert.write(resp.plaintext)

                    print(
                        (
                            "Downloaded: "
                            + str(round(convert.getLength(), 2))
                            + " / "
                            + str(segmentLength)
                        )
                        + (" " * 10)
                        + "\r",
                        end="",
                    )

                    detectedLength = convert.getLength()
                    if (
                        detectedLength
                        > segmentLength + self.padding
                        # > 10  # temp
                    ):
                        print("Downloaded!" + " " * 20)
                        fileName = "./output/" + str(date) + ".mp4"
                        print("Converting...")
                        convert.save(fileName, segmentLength, "ffmpeg")
                        print("")
                        print("Saving to " + fileName + "...")
                        return fileName
