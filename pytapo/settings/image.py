from warnings import warn
from pytapo.error import (
    DayNightModeNotSupportedException,
    ImageCommonNotSupportedException,
)


class ImageInterface:
    def __init__(self, perform_request, execute_function, child_id=None):
        """
        Initializes a new Camera instance.

        Parameters:
        perform_request (func): The function used to perform a request.
        execute_function (func): The function used to execute a function.
        child_id (str, optional): The child camera identifier.
        """
        self.perform_request = perform_request
        self.execute_function = execute_function
        self.child_id = child_id

    def __get_image_common(self, field: str) -> str:
        """
        Retrieves the common image settings.

        Parameters:
        field (str): The image field to get.

        Returns:
        str: The image field value.
        """
        data = self.execute_function(
            "getLightFrequencyInfo", {"image": {"name": "common"}}
        )
        if "common" not in data["image"]:
            raise ImageCommonNotSupportedException(
                "Image common not supported by camera"
            )
        fields = data["image"]["common"]
        if field not in fields:
            raise ImageCommonNotSupportedException(
                f"Image common field {field} not supported by camera"
            )
        return fields[field]

    def __set_image_common(self, field: str, value: str):
        """
        Sets the common image settings.

        Parameters:
        field (str): The image field to set.
        value (str): The value to set.
        """
        return self.execute_function(
            "setLightFrequencyInfo", {"image": {"common": {field: value}}}
        )

    def __get_image_switch(self, switch: str) -> str:
        """
        Retrieves the image switch settings.

        Parameters:
        switch (str): The switch to get.

        Returns:
        str: The switch value.
        """
        data = self.execute_function("getLdc", {"image": {"name": ["switch"]}})
        switches = data["image"]["switch"]
        if switch not in switches:
            raise ImageCommonNotSupportedException(
                "Image switch not supported by camera"
            )
        return switches[switch]

    def __set_image_switch(self, switch: str, value: str) -> dict:
        """
        Sets the image switch settings.

        Parameters:
        switch (str): The switch to set.
        value (str): The value to set.
        """
        return self.execute_function("setLdc", {"image": {"switch": {switch: value}}})

    def get_lens_distortion_correction(self):
        """
        Checks if the lens distortion correction is enabled.

        Returns:
        bool: True if enabled, False otherwise.
        """
        return self.__get_image_switch("ldc") == "on"

    def set_lens_distortion_correction(self, enable):
        """
        Enables or disables the lens distortion correction.

        Parameters:
        enable (bool): True to enable, False to disable.
        """
        return self.__set_image_switch("ldc", "on" if enable else "off")

    def get_day_night_mode(self) -> str:
        """
        Retrieves the current day/night mode.

        Returns:
        str: The current day/night mode.
        """
        if not self.child_id:
            return self.__get_image_common("inf_type")
        raw_value = self.get_night_vision_mode_config()["image"]["switch"][
            "night_vision_mode"
        ]
        if raw_value == "inf_night_vision":
            return "on"
        elif raw_value == "md_night_vision":
            return "auto"
        elif raw_value == "wtl_night_vision":
            return "off"

    def set_day_night_mode(self, mode: str) -> dict:
        """
        Sets the day/night mode.

        Parameters:
        mode (str): The mode to set. Allowed values: "off", "on", "auto".
        """
        allowed_modes = ["off", "on", "auto"]
        if mode not in allowed_modes:
            raise DayNightModeNotSupportedException(
                "Day night mode must be one of {allowed_modes}"
            )
        if not self.child_id:
            return self.__set_image_common("inf_type", mode)
        if mode == "on":
            return self.set_night_vision_mode_config("inf_night_vision")
        elif mode == "off":
            return self.set_night_vision_mode_config("wtl_night_vision")
        elif mode == "auto":
            return self.set_night_vision_mode_config("md_night_vision")

    def get_night_vision_mode_config(self) -> dict:
        """
        Retrieves the current night vision mode configuration.

        Returns:
        dict: The current night vision mode configuration.
        """
        return self.execute_function(
            "getNightVisionModeConfig", {"image": {"name": "switch"}}
        )

    def set_night_vision_mode_config(self, mode: str) -> dict:
        """
        Sets the night vision mode configuration.

        Parameters:
        mode (str): The mode to set.
        """
        return self.execute_function(
            "setNightVisionModeConfig",
            {"image": {"switch": {"night_vision_mode": mode}}},
        )

    def get_image_flip_vertical(self) -> bool:
        """
        Checks if the image flip is set to vertical.

        Returns:
        bool: True if set to vertical, False otherwise.
        """
        if self.child_id:
            return (
                self.get_rotation_status()["image"]["switch"]["flip_type"] == "center"
            )
        else:
            return self.__get_image_switch("flip_type") == "center"

    def set_image_flip_vertical(self, enable: bool) -> dict:
        """
        Sets the image flip to vertical.

        Parameters:
        enable (bool): True to set to vertical, False otherwise.
        """
        if self.child_id:
            return self.set_rotation_status("center" if enable else "off")
        else:
            return self.__set_image_switch("flip_type", "center" if enable else "off")

    def set_rotation_status(self, flip_type: str) -> dict:
        """
        Sets the rotation status.

        Parameters:
        flip_type (str): The type of flip to set.
        """
        return self.execute_function(
            "setRotationStatus",
            {"image": {"switch": {"flip_type": flip_type}}},
        )

    def get_rotation_status(self) -> dict:
        """
        Retrieves the rotation status.

        Returns:
        dict: The rotation status.
        """
        return self.execute_function(
            "getRotationStatus", {"image": {"name": "switch"}}
        )

    def get_force_whitelamp_state(self) -> bool:
        """
        Checks if the force whitelamp state is enabled.

        Returns:
        bool: True if enabled, False otherwise.
        """
        return self.__get_image_switch("force_wtl_state") == "on"

    def set_force_whitelamp_state(self, enable: bool) -> dict:
        """
        Enables or disables the force whitelamp state.

        Parameters:
        enable (bool): True to enable, False to disable.
        """
        return self.__set_image_switch("force_wtl_state", "on" if enable else "off")

    def get_common_image(self) -> dict:
        """
        Retrieves the common image settings.

        Returns:
        dict: The common image settings.
        """
        warn("Prefer to use a specific value getter", DeprecationWarning, stacklevel=2)
        return self.perform_request({"method": "get", "image": {"name": "common"}})

    def getForceWhitelampState(self) -> bool:
        """
        Checks if the force whitelamp state is enabled.

        Returns:
        bool: True if enabled, False otherwise.
        """

        return self.__getImageSwitch("force_wtl_state") == "on"

    def setForceWhitelampState(self, enable: bool) -> dict:
        """
        Enables or disables the force whitelamp state.

        Parameters:
        enable (bool): True to enable, False to disable.
        """

        return self.__setImageSwitch("force_wtl_state", "on" if enable else "off")

    def getImageFlipVertical(self):
        """
        Checks if the image flip is set to vertical.

        Returns:
        bool: True if set to vertical, False otherwise.
        """

        if self.childID:
            return self.getRotationStatus()["image"]["switch"]["flip_type"] == "center"
        else:
            return self.__getImageSwitch("flip_type") == "center"

    def setImageFlipVertical(self, enable):
        """
        Sets the image flip to vertical.

        Parameters:
        enable (bool): True to set to vertical, False otherwise.
        """

        if self.childID:
            return self.setRotationStatus("center" if enable else "off")
        else:
            return self.__setImageSwitch("flip_type", "center" if enable else "off")


    def getLensDistortionCorrection(self, enable: bool) -> dict:
        """
        Checks if the lens distortion correction is enabled.

        Returns:
        bool: True if enabled, False otherwise.
        """
        return self.__getImageSwitch("ldc") == "on"

    def setLensDistortionCorrection(self, enable: bool) -> dict:
        """
        Enables or disables the lens distortion correction.

        Parameters:
        enable (bool): True to enable, False to disable.
        """

        return self.__setImageSwitch("ldc", "on" if enable else "off")