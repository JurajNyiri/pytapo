import logging
import io
import av
import sys

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

    def save(self, fileLocation):
        output = av.open(fileLocation, "w")
        self.openStream()

        input_stream = self.stream.streams.video[0]
        codec_name = input_stream.codec_context.name
        fps = 15
        out_stream = output.add_stream(codec_name, str(fps))
        out_stream.width = input_stream.codec_context.width
        out_stream.height = input_stream.codec_context.height
        out_stream.pix_fmt = input_stream.codec_context.pix_fmt

        for frame in self.stream.decode(input_stream):
            img_frame = frame.to_image()
            out_frame = av.VideoFrame.from_image(img_frame)
            out_packet = out_stream.encode(out_frame)
            output.mux(out_packet)

        out_packet = out_stream.encode(None)
        output.mux(out_packet)

        self.stream.close()
        output.close()

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
