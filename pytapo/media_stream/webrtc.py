"""Native WebRTC streaming and talkback; requires pytapo[webrtc]."""

import asyncio
import logging
import os
import threading
from collections import deque

import av
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaPlayer, MediaRelay
from aiortc.mediastreams import MediaStreamError
from aiortc.rtp import RtcpByePacket
from aiortc.sdp import candidate_from_sdp

from .streamer import Streamer
from .talk import Talk

_LOGGER = logging.getLogger(__name__)


class _FrameQueue(asyncio.Queue):
    """Discard old live frames instead of accumulating latency and memory."""

    def __init__(self, maxsize):
        super().__init__(maxsize=maxsize)
        self._closed = False
        self._pending = deque(maxlen=maxsize)
        self._lock = threading.Lock()

    def put(self, frame):
        # The media thread calls put() before scheduling its coroutine. Retain
        # frames here so a blocked event loop cannot accumulate coroutine args.
        with self._lock:
            if not self._closed:
                self._pending.append(frame)
        return self._flush()

    async def _flush(self):
        with self._lock:
            frames = tuple(self._pending)
            self._pending.clear()
        for frame in frames:
            self.put_nowait(frame)

    def put_nowait(self, frame):
        if self._closed:
            return
        if isinstance(frame, av.VideoFrame):
            # The output encoder must choose its own keyframes, independently
            # of which decoded camera frames survived the queue.
            frame.pict_type = av.video.frame.PictureType.NONE
        if self.full():
            self.get_nowait()
        super().put_nowait(frame)

    def close(self):
        with self._lock:
            self._closed = True
            self._pending.clear()
        while not self.empty():
            self.get_nowait()
        super().put_nowait(None)


class WebRTCSession:
    """One browser connection, using RTSP or the existing direct streamer."""

    def __init__(
        self,
        tapo,
        *,
        source=None,
        quality="HD",
        video_stream=0,
        ff_args=None,
        rtsp_transport="tcp",
        two_way_audio=False,
        ice_servers=(),
        on_error=None,
        on_close=None,
    ):
        self.tapo = tapo
        self.source = source
        self.quality = quality
        self.video_stream = video_stream
        self.ff_args = ff_args or {}
        self.rtsp_transport = rtsp_transport
        self.two_way_audio = two_way_audio
        self.on_error = on_error
        self.on_close = on_close
        self.peer = RTCPeerConnection(
            RTCConfiguration(
                iceServers=[RTCIceServer(**server) for server in ice_servers]
            )
        )
        self._answer_task = None
        self._player = None
        self._relay = MediaRelay()
        self._player_task = None
        self._pipe = None
        self._streamer = None
        self._audio_task = None
        self._timeout_task = None
        self._candidates = []
        self._closed = False
        self._closing_task = None
        self._close_complete = asyncio.Event()

        @self.peer.on("track")
        def on_track(track):
            track._queue = _FrameQueue(maxsize=25 if track.kind == "audio" else 2)
            if (
                track.kind == "audio"
                and self.two_way_audio
                and self._audio_task is None
            ):
                receiver = next(
                    t.receiver
                    for t in self.peer.getTransceivers()
                    if t.receiver.track is track
                )
                handle_rtcp = receiver._handle_rtcp_packet

                async def handle_audio_rtcp(packet):
                    # HA can resume the microphone on this same receiver after
                    # sending BYE. aiortc would otherwise end the track forever.
                    # peer.close() still stops the receiver when the view closes.
                    if not isinstance(packet, RtcpByePacket):
                        await handle_rtcp(packet)

                receiver._handle_rtcp_packet = handle_audio_rtcp
                self._audio_task = asyncio.create_task(self._send_audio(track))

        @self.peer.on("connectionstatechange")
        async def on_connectionstatechange():
            if self.peer.connectionState in ("failed", "closed"):
                await self.close()

    async def answer(self, offer_sdp):
        """Return an SDP answer including the gathered server ICE candidates."""
        self._answer_task = asyncio.current_task()
        try:
            await self.peer.setRemoteDescription(
                RTCSessionDescription(offer_sdp, "offer")
            )
            for candidate in self._candidates:
                await self.peer.addIceCandidate(candidate)
            self._candidates.clear()
            if self.source is None:
                read_fd, write_fd = os.pipe()
                self._pipe = os.fdopen(read_fd, "rb", buffering=0)
                self._streamer = Streamer(
                    self.tapo,
                    quality=self.quality,
                    includeAudio=True,
                    logFunction=lambda message: _LOGGER.debug("%s", message),
                    ff_args={"-map-video": f"0:v:{self.video_stream}", **self.ff_args},
                )
                try:
                    await self._streamer.start(stdout=write_fd)
                finally:
                    os.close(write_fd)
                source = self._pipe
                options = {"probesize": "500000", "analyzeduration": "1000000"}
            else:
                source = self.source
                options = {"rtsp_transport": self.rtsp_transport}
            if self._pipe or str(source).startswith(("rtsp://", "rtsps://")):
                # Match HA's stream path: camera timestamps can jump backwards.
                options["use_wallclock_as_timestamps"] = "1"
            self._player_task = asyncio.create_task(
                asyncio.to_thread(
                    MediaPlayer,
                    source,
                    format="mpegts" if self._pipe else None,
                    options=options,
                    timeout=(10, 5),
                )
            )
            self._player = await asyncio.wait_for(asyncio.shield(self._player_task), 15)
            if self._pipe:
                # This MPEG-TS pipe is live, rather than a file to pace by PTS.
                self._player._throttle_playback = False
            # aiortc 1.16's player queues are unbounded, and its worker does not
            # wait for put() to finish. A bounded Queue alone would leave pending
            # put coroutines holding frames when an encoder or viewer falls behind.
            for track in (self._player.video, self._player.audio):
                if track:
                    track._queue = _FrameQueue(
                        maxsize=2 if track.kind == "video" else 25
                    )
            if self._player.video is None:
                raise RuntimeError("Camera stream has no video track")
            # Sender.stop() must not join the player's thread on the event loop:
            # a Direct decoder can be waiting for data produced by that same loop.
            self.peer.addTrack(
                self._relay.subscribe(self._player.video, buffered=False)
            )
            if self._player.audio:
                audio = self._relay.subscribe(self._player.audio)
                audio._queue = _FrameQueue(maxsize=25)
                self.peer.addTrack(audio)
            await self.peer.setLocalDescription(await self.peer.createAnswer())
            self._timeout_task = asyncio.create_task(self._connection_timeout())
            return self.peer.localDescription.sdp
        except BaseException:
            await self.close()
            raise
        finally:
            self._answer_task = None

    async def add_candidate(self, candidate):
        """Accept a browser RTCIceCandidateInit dictionary."""
        value = None
        if candidate and candidate.get("candidate"):
            value = candidate_from_sdp(
                candidate["candidate"].removeprefix("candidate:")
            )
            value.sdpMid = candidate.get("sdpMid")
            value.sdpMLineIndex = candidate.get("sdpMLineIndex")
        if self.peer.remoteDescription is None:
            self._candidates.append(value)
        else:
            await self.peer.addIceCandidate(value)

    async def _send_audio(self, track):
        resampler = av.AudioResampler(
            format="s16", layout="mono", rate=8000, frame_size=160
        )
        encoder = av.CodecContext.create("pcm_alaw", "w")
        encoder.sample_rate = 8000
        encoder.layout = "mono"
        encoder.format = "s16"

        def encode(frame):
            return [
                bytes(packet)
                for chunk in resampler.resample(frame)
                for packet in encoder.encode(chunk)
            ]

        try:
            # Wait for actual incoming audio before taking the camera's speaker.
            while True:
                frame = await track.recv()
                async with Talk(self.tapo) as talk:
                    while True:
                        for packet in await asyncio.to_thread(encode, frame):
                            await talk.write(packet)
                        try:
                            frame = await asyncio.wait_for(track.recv(), timeout=1)
                        except TimeoutError:
                            # HA stops sending when talk is disabled. Release
                            # the speaker and reopen it when microphone frames resume.
                            break
        except MediaStreamError:
            pass
        except Exception as error:
            try:
                if self.on_error:
                    self.on_error(error)
            finally:
                await self.close()
        finally:
            self._audio_task = None

    async def _connection_timeout(self):
        await asyncio.sleep(30)
        if self.peer.connectionState != "connected":
            await self.close()

    async def close(self):
        """Release the media process, pipe, speaker session and WebRTC peer."""
        if self._closed:
            # Cancelled media tasks must not wait for the closer awaiting them.
            if asyncio.current_task() not in (
                self._closing_task,
                self._answer_task,
                self._audio_task,
                self._timeout_task,
            ):
                await self._close_complete.wait()
            return
        self._closed = True
        self._closing_task = asyncio.current_task()
        try:
            tasks = [
                task
                for task in (self._answer_task, self._audio_task, self._timeout_task)
                if task is not None and task is not asyncio.current_task()
            ]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self._streamer is not None:
                try:
                    async with asyncio.timeout(3):
                        await self._streamer.stop()
                except Exception:
                    process = getattr(self._streamer, "streamProcess", None)
                    if process is not None and process.returncode is None:
                        process.kill()
                        await process.wait()
            if self._player_task is not None and self._player is None:
                try:
                    self._player = await self._player_task
                except Exception:
                    pass
            if self._player:
                for track in (self._player.audio, self._player.video):
                    if track:
                        if isinstance(track._queue, _FrameQueue):
                            track._queue.close()
                        # MediaPlayer tracks share a worker owned by this event loop.
                        track.stop()
            if self._pipe:
                self._pipe.close()
            await self.peer.close()
            if self.on_close:
                self.on_close()
        finally:
            self._close_complete.set()
