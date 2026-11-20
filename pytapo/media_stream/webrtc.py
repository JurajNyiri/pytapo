"""Native WebRTC streaming and talkback; requires pytapo[webrtc]."""

import asyncio
import logging
import os

import av
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaPlayer
from aiortc.mediastreams import MediaStreamError
from aiortc.sdp import candidate_from_sdp

from .streamer import Streamer
from .talk import Talk

_LOGGER = logging.getLogger(__name__)


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
        self._player_task = None
        self._pipe = None
        self._streamer = None
        self._audio_task = None
        self._timeout_task = None
        self._candidates = []
        self._closed = False

        @self.peer.on("track")
        def on_track(track):
            if (
                track.kind == "audio"
                and self.two_way_audio
                and self._audio_task is None
            ):
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
            self._player_task = asyncio.create_task(
                asyncio.to_thread(
                    MediaPlayer,
                    source,
                    format="mpegts" if self._pipe else None,
                    options=options,
                    timeout=5,
                )
            )
            self._player = await asyncio.wait_for(asyncio.shield(self._player_task), 15)
            if self._player.video is None:
                raise RuntimeError("Camera stream has no video track")
            self.peer.addTrack(self._player.video)
            if self._player.audio:
                self.peer.addTrack(self._player.audio)
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
            frame = await track.recv()
            async with Talk(self.tapo) as talk:
                while True:
                    for packet in await asyncio.to_thread(encode, frame):
                        await talk.write(packet)
                    frame = await track.recv()
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
            return
        self._closed = True
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
                    # MediaPlayer tracks share a worker owned by this event loop.
                    track.stop()
        if self._pipe:
            self._pipe.close()
        await self.peer.close()
        if self.on_close:
            self.on_close()
