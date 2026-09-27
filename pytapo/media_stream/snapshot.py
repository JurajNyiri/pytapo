import json
from ..media_stream._utils import StreamType


async def getRecordingSnapshot(tapo, startTime, timeout=8):
    """Return the JPEG the camera keeps for the recording that starts at startTime.

    The Tapo app shows one thumbnail per SD card recording. It comes from the media
    port, with the same request the app uses to download a clip, but with
    media_type 2 and only a start_time: the camera answers with a single
    image/jpeg part (640x360 on a C510W) and then stream_status "finished".
    A media session is bound to the media type of its first request, so this
    opens a session of its own and closes it afterwards; several snapshots can be
    fetched in a row with getRecordingSnapshots.

    Returns the JPEG bytes, or None if the camera has no image for that time. For a
    start_time that does not match a recording the camera acknowledges the request
    and then stays silent, so that case costs the full timeout (a snapshot itself
    arrives within a second or two).
    """
    async for image in getRecordingSnapshots(tapo, [startTime], timeout=timeout):
        return image
    return None


async def getRecordingSnapshots(tapo, startTimes, timeout=8):
    """Yield the JPEG (or None) for each start time, on one media session."""
    mediaSession = tapo.getMediaSession(StreamType.Download)
    mediaSession.set_window_size(50)
    async with mediaSession:
        for seq, startTime in enumerate(startTimes, start=1):
            payload = json.dumps(
                {
                    "type": "request",
                    "seq": seq,
                    "params": {
                        "download": {
                            "client_id": tapo.getUserID(),
                            "channels": [0],
                            "media_type": 2,
                            "start_time": str(startTime),
                            "player_id": tapo.playerID,
                        },
                        "method": "get",
                    },
                }
            )
            image = None
            stream = mediaSession.transceive(payload, no_data_timeout=timeout)
            try:
                async for resp in stream:
                    if resp.mimetype == "image/jpeg":
                        image = bytes(resp.plaintext)
                    elif resp.mimetype == "application/json":
                        try:
                            data = json.loads(resp.plaintext.decode())
                        except (ValueError, AttributeError):
                            continue
                        params = data.get("params") or {}
                        if data.get("type") == "response" and params.get("error_code", 0) not in (0, None):
                            tapo.logger.debugLog(
                                f"Camera refused the snapshot request: {params.get('error_code')}"
                            )
                            break
                        if params.get("event_type") == "stream_status" and params.get("status") == "finished":
                            break
            finally:
                try:
                    await stream.aclose()
                except (AttributeError, RuntimeError, StopAsyncIteration):
                    pass
            yield image
