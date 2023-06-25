from pytapo.error import PresetNotFoundException


class PresetInterface:
    """
    Represents a preset interface for the device, providing methods to interact with and manipulate device presets.
    """

    def __init__(self, execute_function):
        """
        Initiate a new instance of the class.
        The executeFunction argument is a function to call the respective API endpoint.

        Parameters:
        execute_function (callable): Function to execute API calls.
        """
        self.execute_function = execute_function
        self.presets = {}

    def getPresets(self):
        """
        Retrieves the presets available for the device.

        Returns:
        dict: Dictionary of preset IDs and their corresponding names.
        """
        data = self.execute_function("getPresetConfig", {"preset": {"name": ["preset"]}})
        self.presets = {
            id: data["preset"]["preset"]["name"][key]
            for key, id in enumerate(data["preset"]["preset"]["id"])
        }
        return self.presets

    def savePreset(self, name):
        """
        Saves the current device position as a preset with the given name.

        Parameters:
        name (str): The name for the new preset.

        Returns:
        bool: True if operation was successful.
        """
        self.execute_function(
            "addMotorPostion",  # yes, there is a typo in function name
            {"preset": {"set_preset": {"name": str(name), "save_ptz": "1"}}},
        )
        self.getPresets()
        return True

    def deletePreset(self, presetID):
        """
        Deletes a preset from the device.

        Parameters:
        presetID (str or int): The ID of the preset to delete.

        Returns:
        bool: True if operation was successful.

        Raises:
        PresetNotFoundException: If the preset ID is not found.
        """
        if str(presetID) not in self.presets:
            raise PresetNotFoundException(
                f"Preset {str(presetID)} is not set in the app"
            )

        self.execute_function(
            "deletePreset", {"preset": {"remove_preset": {"id": [presetID]}}}
        )
        self.getPresets()
        return True

    def setPreset(self, presetID):
        """
        Sets the device to a preset position.

        Parameters:
        presetID (str or int): The ID of the preset to set.

        Returns:
        dict: Result of the operation.

        Raises:
        PresetNotFoundException: If the preset ID is not found.
        """
        if str(presetID) not in self.presets:
            raise PresetNotFoundException(
                f"Preset {str(presetID)} is not set in the app"
            )
        return self.execute_function(
            "motorMoveToPreset", {"preset": {"goto_preset": {"id": str(presetID)}}}
        )

    def isSupportingPresets(self):
        try:
            return self.getPresets()
        except Exception:
            return False
