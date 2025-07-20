#!/usr/bin/env python3
import asyncio
import os
import sys

from pytapo import Tapo
from pytapo.media_stream.streamer import Streamer

# ── ENVIRONMENT ────────────────────────────────────────────────────────────
host = os.environ["HOST"]
password_cloud = os.environ["PASSWORD_CLOUD"]
stream_port = os.environ.get("STREAM_PORT")
control_port = os.environ.get("CONTROL_PORT")
enable_audio = os.environ.get("ENABLE_AUDIO", "no").lower() == "yes"
# ───────────────────────────────────────────────────────────────────────────

print("Connecting to camera …")
tapo = Tapo(
    host,
    "admin",
    password_cloud,
    password_cloud,
    controlPort=control_port,
    streamPort=stream_port,
)


def callback(status: dict):
    print(status)


async def main():
    streamer = Streamer(
        tapo,
        logFunction=callback,
        includeAudio=enable_audio,
        mode="pipe",
        analyzeDuration=2000000,
        probeSize="512k",
    )
    info = await streamer.start()
    fd = info["read_fd"]

    os.set_inheritable(fd, True)

    print(f"Starting VLC on fd://{fd} …")
    vlc = await asyncio.create_subprocess_exec(
        "/Applications/VLC.app/Contents/MacOS/VLC",
        f"fd://{fd}",
        "--demux=ts",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
        pass_fds=(fd,),
    )

    try:
        await vlc.wait()
    finally:
        await streamer.stop()
        vlc.terminate()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
