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
stream_from_device_mac = os.environ.get("STREAM_FROM_MAC")

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


def callback(status):
    print(status)
    pass


keepRunningFor = 6000


async def download_async():
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
    ranFor = 0
    streamer = Streamer(
        tapoDevice,
        logFunction=callback,
        outputDirectory=outputDir,
        includeAudio=True if enable_audio == "yes" else False,
        mode="hls",
        quality="VGA",
    )
    pids = await streamer.start()
    print(pids)

    while True:
        ranFor += 1
        await asyncio.sleep(1)  # Use asyncio.sleep()
        if ranFor > keepRunningFor:
            await streamer.stop()
            break
    print("")


if __name__ == "__main__":
    asyncio.run(download_async())
