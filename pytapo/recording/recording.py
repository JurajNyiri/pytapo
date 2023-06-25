from datetime import datetime
from warnings import warn
from pytapo.error import (
    RecordingNotSupportedException,
)


class RecordingInterface:
    def __init__(self, perform_request, execute_function, child_id=None):
        """
        Initializes a new Recording instance.
        Parameters:
        child_id (str, optional): The child camera identifier.
        """
        self.child_id = child_id
        self.perform_request = perform_request
        self.execute_function = execute_function

    ...
    # Other methods here
    ...

    def get_recordings_list(self, start_date="20000101", end_date=None) -> list:
        """
        Retrieves the list of recordings for a specific date range.

        Parameters:
        start_date (str, optional): The start date in the format "YYYYMMDD".
                                    Defaults to "20000101".
        end_date (str, optional): The end date in the format "YYYYMMDD".
                                Defaults to the current date.

        Returns:
        list: The list of recordings.
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y%m%d")
        result = self.execute_function(
            "searchDateWithVideo",
            {
                "playback": {
                    "search_year_utility": {
                        "channel": [0],
                        "end_date": end_date,
                        "start_date": start_date,
                    }
                }
            },
        )
        if "playback" not in result:
            raise RecordingNotSupportedException(
                "Video playback is not supported by this camera"
            )
        return result["playback"]["search_results"]

    def get_recordings(self, date, start_index=0, end_index=999999999) -> list:
        """
        Retrieves the recordings for a specific date.

        Parameters:
        date (str): The date to retrieve the recordings for in the format "YYYYMMDD".
        start_index (int, optional): The starting index for the recordings. Defaults to 0.
        end_index (int, optional): The ending index for the recordings.
                                    Defaults to 999999999.

        Returns:
        list: The list of recordings.
        """
        result = self.execute_function(
            "searchVideoOfDay",
            {
                "playback": {
                    "search_video_utility": {
                        "channel": 0,
                        "date": date,
                        "end_index": end_index,
                        "id": self.get_user_id(),
                        "start_index": start_index,
                    }
                }
            },
        )
        if "playback" not in result:
            raise RecordingNotSupportedException(
                "Video playback is not supported by this camera"
            )
        return result["playback"]["search_video_results"]
