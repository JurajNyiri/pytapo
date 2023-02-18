import logging
import io
import av
import ffmpeg
import os

logger = logging.getLogger(__name__)
logging.getLogger("libav").setLevel(logging.ERROR)


class Convert:
    writer = io.BytesIO()
    stream = None
    known_lengths = {}
    addedChunks = 0
    lengthLastCalculatedAtChunk = 0

    def __init__(self):
        pass

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
    def save(self, fileLocation, fileLength, method="av"):
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
        elif method == "ffmpeg":
            tempFileLocation = fileLocation + ".ts"
            file = open(tempFileLocation, "wb")
            file.write(self.writer.getvalue())
            file.close()

            cmd = 'ffmpeg -i "{inputFile}" -y -an "{outputFile}" >/dev/null 2>&1'.format(
                inputFile=tempFileLocation, outputFile=fileLocation
            )
            os.system(cmd)

            os.remove(tempFileLocation)
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

    def write(self, data: bytes):
        self.addedChunks += 1
        return self.writer.write(data)