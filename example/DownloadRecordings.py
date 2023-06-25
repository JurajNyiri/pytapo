from pytapo import Tapo
from pytapo.media_stream.downloader import Downloader
import asyncio
import os
from rich.console import Console
import httpx
import typer

console = Console()

app = typer.Typer()


@app.command()
def download_recordings(
    output_dir: str = typer.Option(
        ..., help="Directory path where videos will be saved"
    ),
    date: str = typer.Option(
        ..., help="Date to download recordings for in format YYYYMMDD"
    ),
    host: str = typer.Option(..., help="Camera IP"),
    password_cloud: str = typer.Option(..., help="Your cloud password"),
    window_size: int = typer.Option(
        50,
        help="Prefferred window size, affects download speed and stability, recommended: 50",
    ),
):
    console.log("Connecting to camera...")
    tapo = Tapo(host, "admin", password_cloud, password_cloud)

    async def download_async():
        async with httpx.AsyncClient() as client:
            console.log("Getting recordings...")
            recordings = await client.get(tapo.getRecordings(date))
            for recording in recordings:
                for key in recording:
                    downloader = Downloader(
                        tapo,
                        recording[key]["startTime"],
                        recording[key]["endTime"],
                        output_dir,
                        None,
                        False,
                        window_size,
                    )
                    async for status in downloader.download():
                        statusString = (
                            status["currentAction"] + " " + status["fileName"]
                        )
                        if status["progress"] > 0:
                            statusString += (
                                ": "
                                + str(round(status["progress"], 2))
                                + " / "
                                + str(status["total"])
                            )
                        else:
                            statusString += "..."
                        console.log(
                            statusString + (" " * 10) + "\r",
                            end="",
                        )
                    console.log("")

    loop = asyncio.get_event_loop()
    loop.run_until_complete(download_async())


if __name__ == "__main__":
    app()
# python your_script.py --output_dir /path/to/dir --date 20230624 --host 192.168.1.1 --password_cloud your_password --window_size 50
