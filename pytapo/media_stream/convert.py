import logging
import io
import av

logger = logging.getLogger(__name__)
logging.getLogger("libav").setLevel(logging.ERROR)


class Convert:
    writer = io.BytesIO()
    stream = None

    def __init__(self):
        print("init")

    # todo: optimize to use buffer instead
    def openStream(self):
        self.stream = av.open(self.writer, mode="r")

    def getLength(self):
        self.writer.seek(io.SEEK_SET)
        self.openStream()

        stream = self.stream.streams.video[0]

        firstTime = None
        lastTime = None
        for frame in self.stream.decode(stream):
            if firstTime is None:
                firstTime = float(frame.pts * stream.time_base)
            lastTime = float(frame.pts * stream.time_base)

        self.writer.seek(0, io.SEEK_END)
        return lastTime - firstTime

    def write(self, data: bytes):
        return self.writer.write(data)
