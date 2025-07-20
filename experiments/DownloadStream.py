import asyncio
import os
from pytapo import Tapo
from pytapo.media_stream.streamer import Streamer

# mandatory
outputDir = os.environ.get("OUTPUT")  # directory path where videos will be saved
host = os.environ.get("HOST")  # change to camera IP
password_cloud = os.environ.get("PASSWORD_CLOUD")  # set to your cloud password
stream_port = os.environ.get("STREAM_PORT")
control_port = os.environ.get("CONTROL_PORT")
enable_audio = os.environ.get("ENABLE_AUDIO")

# optional
window_size = os.environ.get(
    "WINDOW_SIZE"
)  # set to prefferred window size, affects download speed and stability, recommended: 50

print("Connecting to camera...")
tapo = Tapo(
    host,
    "admin",
    password_cloud,
    password_cloud,
    controlPort=control_port,
    streamPort=stream_port,
)


def callback(status):
    print(status)
    pass


keepRunningFor = 6000


async def download_async():
    print("Getting recordings...")
    ranFor = 0
    downloader = Streamer(
        tapo,
        logFunction=callback,
        outputDirectory=outputDir,
        includeAudio=True if enable_audio == "yes" else False,
        mode="hls",
    )
    pids = await downloader.start()
    print(pids)

    while True:
        ranFor += 1
        await asyncio.sleep(1)  # Use asyncio.sleep()
        if ranFor > keepRunningFor:
            await downloader.stop()
            break
    print("")


if __name__ == "__main__":
    asyncio.run(download_async())
