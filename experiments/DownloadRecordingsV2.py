from pytapo import Tapo
from pytapo.media_stream.downloaderv2 import DownloaderV2
import asyncio
import os

# mandatory
outputDir = os.environ.get("OUTPUT")  # directory path where videos will be saved
date = os.environ.get("DATE")  # date to download recordings for in format YYYYMMDD
host = os.environ.get("HOST")  # change to camera IP
password_cloud = os.environ.get("PASSWORD_CLOUD")  # set to your cloud password
enable_audio = os.environ.get("ENABLE_AUDIO")

# optional
window_size = os.environ.get(
    "WINDOW_SIZE"
)  # set to prefferred window size, affects download speed and stability, recommended: 50

print("Connecting to camera...")
tapo = Tapo(host, "admin", password_cloud, password_cloud, printDebugInformation=False)

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


async def downloadAll(childrenDevices):
    for macAddress in childrenDevices:
        child = childrenDevices[macAddress]
        await download_async(child, macAddress)


def callback(status):
    print(status)
    pass


async def download_async(tapo: Tapo, fileNamePrefix=""):
    print("Getting recordings...")
    recordings = await asyncio.get_event_loop().run_in_executor(
        None, tapo.getRecordings, date
    )
    print("Getting time correction...")
    timeCorrection = await asyncio.get_event_loop().run_in_executor(
        None, tapo.getTimeCorrection
    )
    print("Looping through recordings...")
    for recording in recordings:
        for key in recording:

            ranFor = 0
            streamer = DownloaderV2(
                tapo,
                recording[key]["startTime"],
                recording[key]["endTime"],
                timeCorrection,
                logFunction=callback,
                outputDirectory=outputDir,
                includeAudio=True if enable_audio == "yes" else False,
                fileName=f"{recording[key]["startTime"]}-{recording[key]["endTime"]}.mp4",
                mode="mp4",
                quality="VGA",
            )
            pids = await streamer.start()
            print(pids)

            while True:
                if streamer.running:
                    print(
                        f"Downloading: {streamer.downloadedSeconds} / {streamer.duration}"
                    )
                    ranFor += 1
                    await asyncio.sleep(0.1)
                else:

                    break


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    if childrenDevices:
        loop.run_until_complete(downloadAll(childrenDevices))
    else:
        loop.run_until_complete(download_async(tapo))
