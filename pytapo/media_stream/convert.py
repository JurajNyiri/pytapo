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

        test_input = self.stream
        test_output = av.open("output_vid.mp4", "w")

        in_stream = test_input.streams.video[0]
        # out_stream = test_output.add_stream(template=in_stream)  # Using template=in_stream is not working (probably meant to be used for re-muxing and not for re-encoding).

        codec_name = (
            in_stream.codec_context.name
        )  # Get the codec name from the input video stream.
        fps = 15
        print(codec_name)
        print(in_stream.codec_context)
        out_stream = test_output.add_stream(codec_name, str(fps))
        out_stream.width = (
            in_stream.codec_context.width
        )  # Set frame width to be the same as the width of the input stream
        out_stream.height = (
            in_stream.codec_context.height
        )  # Set frame height to be the same as the height of the input stream
        out_stream.pix_fmt = (
            in_stream.codec_context.pix_fmt
        )  # Copy pixel format from input stream to output stream
        # stream.options = {'crf': '17'}  # Select low crf for high quality (the price is larger file size).

        for frame in test_input.decode(in_stream):
            img_frame = frame.to_image()
            out_frame = av.VideoFrame.from_image(
                img_frame
            )  # Note: to_image and from_image is not required in this specific example.
            out_packet = out_stream.encode(out_frame)  # Encode video frame
            test_output.mux(
                out_packet
            )  # "Mux" the encoded frame (add the encoded frame to MP4 file).
            print(out_packet)

        # Flush the encoder
        out_packet = out_stream.encode(None)
        test_output.mux(out_packet)

        test_input.close()
        test_output.close()

        return
        in_stream = self.stream.streams.video[0]
        out_stream = output.add_stream("libx264", 24)
        out_stream.width = 1920
        out_stream.height = 1080
        out_stream.pix_fmt = "yuv420p"

        for packet in self.stream.demux(in_stream):
            print(packet)

            # We need to skip the "flushing" packets that `demux` generates.
            if packet.dts is None:
                continue

            # We need to assign the packet to the new stream.
            packet.stream = out_stream
            output.mux(packet)
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
