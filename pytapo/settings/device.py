from datetime import datetime
from pytapo.error import SettingsException


class DeviceInterface:
    def __init__(self, perform_request, execute_function, childID=None):
        """
        Constructs a new DeviceInterface instance.

        Parameters:
        perform_request (func): The function used to perform a request.
        execute_function (func): The function used to execute a function.
        childID (str, optional): The child device identifier.
        """
        self.perform_request = perform_request
        self.execute_function = execute_function
        self.childID = childID
        self.timeCorrection = False

    def setPrivacyMode(self, enabled: bool) -> dict:
        """
        Controls the privacy mode of the device.

        Parameters:
        enabled (bool): Privacy mode status to set.
        """
        return self.execute_function(
            "setLensMaskConfig",
            {"lens_mask": {"lens_mask_info": {"enabled": "on" if enabled else "off"}}},
        )

    def setMediaEncrypt(self, enabled: bool) -> dict:
        """
        Controls the media encryption of the device.

        Parameters:
        enabled (bool): Media encryption status to set.
        """
        return self.execute_function(
            "setMediaEncrypt",
            {"cet": {"media_encrypt": {"enabled": "on" if enabled else "off"}}},
        )

    def getPrivacyMode(self) -> dict:
        """
        Fetches the current privacy mode of the device.

        Returns:
        dict: Current privacy mode configuration.
        """
        data = self.execute_function(
            "getLensMaskConfig",
            {"lens_mask": {"name": ["lens_mask_info"]}},
        )
        return data["lens_mask"]["lens_mask_info"]

    def getMediaEncrypt(self) -> dict:
        """
        Fetches the current media encryption of the device.

        Returns:
        dict: Current media encryption configuration.
        """
        data = self.execute_function(
            "getMediaEncrypt",
            {"cet": {"name": ["media_encrypt"]}},
        )
        return data["cet"]["media_encrypt"]

    def getRotationStatus(self) -> dict:
        """
        Retrieves the current rotation status of the device.

        Returns:
        dict: Current rotation status.
        """
        return self.execute_function(
            "getRotationStatus",
            {"image": {"name": ["switch"]}},
        )

    def getAutoTrackTarget(self) -> dict:
        """
        Retrieves the current auto track target configuration of the device.

        Returns:
        dict: Current auto track target configuration.
        """
        return self.execute_function(
            "getTargetTrackConfig", {"target_track": {"name": ["target_track_info"]}}
        )["target_track"]["target_track_info"]

    def setAutoTrackTarget(self, enabled: bool) -> dict:
        """
        Controls the auto track target configuration of the device.

        Parameters:
        enabled (bool): Auto track target status to set.
        """
        return self.execute_function(
            "setTargetTrackConfig",
            {"target_track": {"target_track_info": {"enabled": "on" if enabled else "off"}}},
        )

    def getAudioSpec(self) -> dict:
        """
        Fetches the device's audio capabilities.
        Note: Not functional for child devices.

        Returns:
        dict: Audio capabilities if available.
        """
        return self.perform_request(
            {
                "method": "get",
                "audio_capability": {"name": ["device_speaker", "device_microphone"]},
            }
        )

    def getVhttpd(self) -> dict:
        """
        Fetches the Vhttpd configuration of the device.
        Note: Not functional for child devices.

        Returns:
        dict: Vhttpd configuration if available.
        """
        return self.perform_request({"method": "get", "cet": {"name": ["vhttpd"]}})

    def getBasicInfo(self) -> dict:
        """
        Retrieves basic information about the device.

        Returns:
        dict: Basic device information.
        """
        return self.execute_function(
            "getDeviceInfo", {"device_info": {"name": ["basic_info"]}}
        )

    def getTime(self) -> dict:
        """
        Retrieves the current time from the device.

        Returns:
        dict: Current device time.
        """
        return self.execute_function(
            "getClockStatus", {"system": {"name": "clock_status"}}
        )

    def getModel(self) -> dict:
        """
        Retrieves the device model.

        Returns:
        dict: Device model.
        """
        return self.execute_function(
            "getDeviceInfo", {"device_info": {"name": ["basic_info"]}}
        )

    # returns empty response for child devices
    def getOsd(self) -> dict:
        # no, asking for all does not work...
        if self.childID:
            return self.execute_function(
                "getOsd",
                {"OSD": {"name": ["logo", "date", "label"]}},
            )
        else:
            return self.execute_function(
                "getOsd",
                {"OSD": {"name": ["date", "week", "font"], "table": ["label_info"]}},
            )

    def setOsd(
        self,
        label,
        dateEnabled=True,
        labelEnabled=False,
        weekEnabled=False,
        dateX=0,
        dateY=0,
        labelX=0,
        labelY=500,
        weekX=0,
        weekY=0,
    ) -> dict:
        """
        Sets the OSD configuration of the device.

        Parameters:
        label (str): The label to display on the OSD.
        dateEnabled (bool, optional): Whether to display the date on the OSD.
        labelEnabled (bool, optional): Whether to display the label on the OSD.
        weekEnabled (bool, optional): Whether to display the week on the OSD.
        dateX (int, optional): The X coordinate of the date on the OSD.
        dateY (int, optional): The Y coordinate of the date on the OSD.
        labelX (int, optional): The X coordinate of the label on the OSD.

        Returns:
        dict: OSD configuration.

        Raises:
        SettingsException: If the label is too long or the coordinates are invalid.
        """
        if self.childID:
            raise SettingsException(
                "Error: OSD settings not available for child devices"
            )
        data = {
            "method": "set",
            "OSD": {
                "date": {
                    "enabled": "on" if dateEnabled else "off",
                    "x_coor": dateX,
                    "y_coor": dateY,
                },
                "week": {
                    "enabled": "on" if weekEnabled else "off",
                    "x_coor": weekX,
                    "y_coor": weekY,
                },
                "font": {
                    "color": "white",
                    "color_type": "auto",
                    "display": "ntnb",
                    "size": "auto",
                },
                "label_info_1": {
                    "enabled": "on" if labelEnabled else "off",
                    "x_coor": labelX,
                    "y_coor": labelY,
                },
            },
        }

        if len(label) >= 16:
            raise SettingsException("Error: Label must be less than 16 characters")
        elif len(label) == 0:
            data["OSD"]["label_info_1"]["enabled"] = "off"
        else:
            data["OSD"]["label_info_1"]["text"] = label
        if (
            dateX > 10000
            or dateX < 0
            or labelX > 10000
            or labelX < 0
            or weekX > 10000
            or weekX < 0
            or dateY > 10000
            or dateY < 0
            or labelY > 10000
            or labelY < 0
            or weekY > 10000
            or weekY < 0
        ):
            raise SettingsException("Error: Coordinates must be between 0 and 10000")

        return self.perform_request(data)

    # does not work for child devices, function discovery needed
    def getModuleSpec(self) -> dict:
        """
        Retrieves the module specification of the device.

        Returns:
        dict: Module specification.
        """
        return self.perform_request(
            {"method": "get", "function": {"name": ["module_spec"]}}
        )

    def getChildDevices(self) -> list:
        """
        Retrieves the child devices of the device.

        Returns:
        list: Child devices.
        """

        childDevices = self.perform_request(
            {
                "method": "getChildDeviceList",
                "params": {"childControl": {"start_index": 0}},
            }
        )
        return childDevices["result"]["child_device_list"]

    def getTimeCorrection(self) -> int:
        if self.timeCorrection is False:
            currentTime = self.getTime()

            timeReturned = (
                "system" in currentTime
                and "clock_status" in currentTime["system"]
                and "seconds_from_1970" in currentTime["system"]["clock_status"]
            )
            if timeReturned:
                nowTS = int(datetime.timestamp(datetime.now()))
                self.timeCorrection = (
                    nowTS - currentTime["system"]["clock_status"]["seconds_from_1970"]
                )
        return self.timeCorrection

    def getEvents(self, startTime=False, endTime=False) -> list:
        timeCorrection = self.getTimeCorrection()
        if timeCorrection is False:
            raise SettingsException("Error: Could not get time correction")

        nowTS = int(datetime.timestamp(datetime.now()))
        if startTime is False:
            startTime = nowTS + (-1 * timeCorrection) - (10 * 60)
        if endTime is False:
            endTime = nowTS + (-1 * timeCorrection) + 60

        responseData = self.execute_function(
            "searchDetectionList",
            {
                "playback": {
                    "search_detection_list": {
                        "start_index": 0,
                        "channel": 0,
                        "start_time": startTime,
                        "end_time": endTime,
                        "end_index": 999,
                    }
                }
            },
        )
        events = []

        detectionsReturned = (
            "playback" in responseData
            and "search_detection_list" in responseData["playback"]
        )

        if detectionsReturned:
            for event in responseData["playback"]["search_detection_list"]:
                event["start_time"] = event["start_time"] + timeCorrection
                event["end_time"] = event["end_time"] + timeCorrection
                event["startRelative"] = nowTS - event["start_time"]
                event["endRelative"] = nowTS - event["end_time"]
                events.append(event)
        return events

    def format(self) -> dict:
        """
        Formats the SD card of the device.
        """
        return self.execute_function(
            "formatSdCard", {"harddisk_manage": {"format_hd": "1"}}
        )  # pragma: no cover

    def startFirmwareUpgrade(self) -> None:
        """
        Starts the firmware upgrade process.

        Raises:
        SettingsException: If the firmware upgrade could not be started.
        """
        try:
            self.performRequest(
                {"method": "do", "cloud_config": {"fw_download": "null"}}
            )
        except Exception as e:
            raise SettingsException("Error: Could not start firmware upgrade") from e

    def isUpdateAvailable(self) -> bool:
        """
        Checks if a firmware update is available.

        Returns:
        bool: True if an update is available, False otherwise.
        """
        return self.performRequest(
            {
                "method": "multipleRequest",
                "params": {
                    "requests": [
                        {
                            "method": "checkFirmwareVersionByCloud",
                            "params": {"cloud_config": {"check_fw_version": "null"}},
                        },
                        {
                            "method": "getCloudConfig",
                            "params": {"cloud_config": {"name": ["upgrade_info"]}},
                        },
                    ]
                },
            }
        )