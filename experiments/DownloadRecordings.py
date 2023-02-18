from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader
import asyncio
import os

outputDir = os.environ.get("output")  # directory path where videos will be saved
date = os.environ.get("date")  # date to download recordings for in format YYYYMMDD
host = os.environ.get("host")  # change to camera IP
user = os.environ.get("user")  # your username
password = os.environ.get("password")  # your password
password_cloud = os.environ.get("password_cloud")  # set to your cloud password

print("Connecting to camera...")
tapo = Tapo(host, user, password, password_cloud)


async def download_async():
    print("Getting recordings...")
    recordings = tapo.getRecordings(date)
    for recording in recordings:
        for key in recording:
            downloader = Downloader(
                tapo, recording[key]["startTime"], recording[key]["endTime"], outputDir,
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
                    statusString + (" " * 10) + "\r", end="",
                )
            print("")


loop = asyncio.get_event_loop()
loop.run_until_complete(download_async())

