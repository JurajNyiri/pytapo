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
stream_from_device_mac = os.environ.get("STREAM_FROM_MAC")
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


childrenDevices = {}
try:
    for child in tapo.getChildDevices():
        print("Connecting to " + child["device_name"] + "...")
        childrenDevices[child["mac"].replace(":", "")] = Tapo(
            host,
            "admin",
            password_cloud,
            password_cloud,
            childID=child["device_id"],
        )
except Exception:
    print("Device is not a hub.")
    pass


async def main():
    if childrenDevices:
        if stream_from_device_mac in childrenDevices:
            tapoDevice = childrenDevices[stream_from_device_mac.replace(":", "")]
        else:
            print(
                "Error: You need to set STREAM_FROM_MAC environment variable, choose from below:"
            )
            for mac in childrenDevices:
                print(mac)
            raise Exception("You need to set STREAM_FROM_MAC environment variable.")
    else:
        tapoDevice = tapo
    print("Starting stream...")
    streamer = Streamer(
        tapoDevice,
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
