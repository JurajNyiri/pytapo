import logging
import io
import av
import ffmpeg
import os
import datetime

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

    def saveWithAV(self, fileLocation, fileLength):
        self.openStream()
        output = av.open(fileLocation, "w")

        input_stream = self.stream.streams.video[0]
        codec_name = input_stream.codec_context.name
        fps = 15
        out_stream = output.add_stream(codec_name, str(fps))
        out_stream.width = input_stream.codec_context.width
        out_stream.height = input_stream.codec_context.height
        out_stream.pix_fmt = input_stream.codec_context.pix_fmt

        firstTime = None
        for frame in self.stream.decode(input_stream):
            if firstTime is None:
                firstTime = float(frame.pts * input_stream.time_base)
            currentFrameTime = float(frame.pts * input_stream.time_base)
            currentLength = currentFrameTime - firstTime
            if currentLength > fileLength:
                print("Converted!" + " " * 20)
                break
            print(
                ("Converted: " + str(round(currentLength, 2)) + " / " + str(fileLength))
                + (" " * 10)
                + "\r",
                end="",
            )
            img_frame = frame.to_image()
            out_frame = av.VideoFrame.from_image(img_frame)
            out_packet = out_stream.encode(out_frame)
            output.mux(out_packet)

        out_packet = out_stream.encode(None)
        output.mux(out_packet)

        self.stream.close()
        output.close()

    # cuts and saves the video
    def save(self, fileLocation, fileLength, method="ffmpeg"):
        # todo: does not work with audio yet
        if method == "av":
            return self.saveWithAV(fileLocation, fileLength)
        elif method == "ffmpeg-python":
            raise Exception("Not implemented")
            # todo
            tempFileLocation = fileLocation + ".ts"
            file = open(tempFileLocation, "wb")
            file.write(self.writer.getvalue())
            file.close()

            input = ffmpeg.input(tempFileLocation)
            out = ffmpeg.output(None, input.video, fileLocation).run_async(
                pipe_stdin=True
            )
            print(out)
        elif method == "ffmpeg":  # recommended, fastest and works with audio
            tempVideoFileLocation = fileLocation + ".ts"
            file = open(tempVideoFileLocation, "wb")
            file.write(self.writer.getvalue())
            file.close()
            tempAudioFileLocation = fileLocation + ".alaw"
            file = open(tempAudioFileLocation, "wb")
            file.write(self.audioWriter.getvalue())
            file.close()

            cmd = 'ffmpeg -ss 00:00:00 -i "{inputVideoFile}" -f alaw -ar 8000 -i "{inputAudioFile}" -t {videoLength} -y -c:v copy -c:a aac -map 0:v:0 -map 1:a:0 "{outputFile}"'.format(
                inputVideoFile=tempVideoFileLocation,
                inputAudioFile=tempAudioFileLocation,
                outputFile=fileLocation,
                videoLength=str(datetime.timedelta(seconds=fileLength)),
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

    # todo: optimize to use buffer instead
    def openStream(self):
        self.writer.seek(io.SEEK_SET)
        self.stream = av.open(self.writer, mode="r")

    # calculates real stream length, hard on processing since it has to go through all the frames
    def calculateLength(self):
        self.openStream()

        stream = self.stream.streams.video[0]

        firstTime = None
        lastTime = None
        for frame in self.stream.decode(stream):
            if firstTime is None:
                firstTime = float(frame.pts * stream.time_base)
            lastTime = float(frame.pts * stream.time_base)

        self.writer.seek(0, io.SEEK_END)

        duration = lastTime - firstTime
        self.known_lengths[self.addedChunks] = duration
        self.lengthLastCalculatedAtChunk = self.addedChunks
        return duration

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
            return self.calculateLength()
        else:
            bytesPerChunk = lastKnownChunk / lastKnownLength
            return self.addedChunks / bytesPerChunk

    def write(self, data: bytes, audioData: bytes):
        self.addedChunks += 1
        return self.writer.write(data) and self.audioWriter.write(audioData)
