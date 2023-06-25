from pytapo.error import LightFrequencyModeNotSupportedException


class LEDInterface:
    """
    An interface for interacting with LED settings on a Tapo device.
    """

    def __init__(self, perform_request, execute_function):
        """
        Initialize the LEDInterface with a function to execute API calls.

        Parameters:
        execute_function (func): The function to be used for making API requests. It should take in a function name and parameters as arguments.
        """
        self.execute_function = execute_function
        self.perform_request = perform_request

    def get_light_frequency_mode(self) -> str:
        """
        Retrieves the current light frequency mode.

        Returns:
        str: The current light frequency mode.
        """
        return self.execute_function("getLightFrequencyMode", {})

    def set_light_frequency_mode(self, mode: str) -> dict:
        """
        Sets the light frequency mode.

        Parameters:
        mode (str): The mode to set the light frequency to. Must be one of ["auto", "50", "60"].

        Returns:
        dict: The result of the set operation.

        Raises:
        Exception: If the provided mode is not one of the allowed modes.
        """
        allowed_modes = ["auto", "50", "60"]
        if mode not in allowed_modes:
            raise LightFrequencyModeNotSupportedException(
                "Light frequency mode must be one of {allowed_modes}"
            )

        return self.execute_function("setLightFrequencyMode", {"mode": mode})

    def set_led_enabled(self, enabled: bool) -> dict:
        """
        Sets whether the LED is enabled or not.

        Parameters:
        enabled (bool): Whether the LED should be enabled.

        Returns:
        dict: The result of the set operation.
        """
        return self.execute_function(
            "setLedStatus", {"led": {"config": {"enabled": "on" if enabled else "off"}}}
        )

    def getLED(self) -> dict:
        """
        Retrieves the current LED status of the device.

        Returns:
        dict: Current LED configuration.
        """
        return self.execute_function(
            "getLedStatus",
            {"led": {"name": ["config"]}},
        )[
            "led"
        ]["config"]
