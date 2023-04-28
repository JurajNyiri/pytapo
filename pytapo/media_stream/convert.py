import logging
import io
import subprocess
import os
import datetime
import tempfile

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

    # cuts and saves the video
    def save(self, fileLocation, fileLength, method="ffmpeg"):
        if method == "ffmpeg":
            tempVideoFileLocation = fileLocation + ".ts"
            file = open(tempVideoFileLocation, "wb")
            file.write(self.writer.getvalue())
            file.close()
            tempAudioFileLocation = fileLocation + ".alaw"
            file = open(tempAudioFileLocation, "wb")
            file.write(self.audioWriter.getvalue())
            file.close()

            cmd = 'ffmpeg -ss 00:00:00 -i "{inputVideoFile}" -f alaw -ar 8000 -i "{inputAudioFile}" -t {videoLength} -y -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 "{outputFile}" >{devnull} 2>&1'.format(
                inputVideoFile=tempVideoFileLocation,
                inputAudioFile=tempAudioFileLocation,
                outputFile=fileLocation,
                videoLength=str(datetime.timedelta(seconds=fileLength)),
                devnull=os.devnull
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

    def write(self, data: bytes, audioData: bytes):
        self.addedChunks += 1
        return self.writer.write(data) and self.audioWriter.write(audioData)
