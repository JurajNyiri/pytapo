from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader
import asyncio
import os

# mandatory
outputDir = os.environ.get("OUTPUT")  # directory path where videos will be saved
date = os.environ.get("DATE")  # date to download recordings for in format YYYYMMDD
host = os.environ.get("HOST")  # change to camera IP
password_cloud = os.environ.get("PASSWORD_CLOUD")  # set to your cloud password

# optional
window_size = os.environ.get(
    "WINDOW_SIZE"
)  # set to prefferred window size, affects download speed and stability, recommended: 50

print("Connecting to camera...")
tapo = Tapo(host, "admin", password_cloud, password_cloud, printDebugInformation=True)


async def download_async():
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
            downloader = Downloader(
                tapo,
                recording[key]["startTime"],
                recording[key]["endTime"],
                timeCorrection,
                outputDir,
                None,
                False,
                window_size,
            )
            async for status in downloader.download():
                statusString = status["currentAction"] + " " + status["fileName"]
                if status["progress"] > 0:
                    statusString += (
                        ": "
                        + str(round(status["progress"], 2))
                        + " / "
                        + str(status["total"])
                    )
                else:
                    statusString += "..."
                print(
                    statusString + (" " * 10) + "\r",
                    end="",
                )
            print("")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(download_async())
