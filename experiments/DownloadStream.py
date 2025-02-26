import asyncio
import os
from pytapo import Tapo
from pytapo.media_stream.streamer import Streamer

# mandatory
outputDir = os.environ.get("OUTPUT")  # directory path where videos will be saved
host = os.environ.get("HOST")  # change to camera IP
password_cloud = os.environ.get("PASSWORD_CLOUD")  # set to your cloud password

# optional
window_size = os.environ.get(
    "WINDOW_SIZE"
)  # set to prefferred window size, affects download speed and stability, recommended: 50

print("Connecting to camera...")
tapo = Tapo(host, "admin", password_cloud, password_cloud)


def callback(status):
    print(status)


keepRunningFor = 10


async def download_async():
    print("Getting recordings...")
    ranFor = 0
    downloader = Streamer(tapo, callback, outputDir)
    await downloader.start_hls()

    while True:
        print("sleeping")
        ranFor += 1
        await asyncio.sleep(1)  # Use asyncio.sleep()
        if ranFor > keepRunningFor:
            await downloader.stop_hls()
            break
    print("")


if __name__ == "__main__":
    asyncio.run(download_async())
