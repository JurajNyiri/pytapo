from pytapo.error import DetectionSensitivityNotSupportedException


class AudioDetection:
    def __init__(self, perform_request, execute_function, childID=None):
        """
        Initializes the AudioDetection class.

        :param perform_request: The function used to perform a request.
        :param execute_function: The function used to execute a function.
        """
        self.perform_request = perform_request
        self.execute_function = execute_function
        self.childID = childID

    def __getSensitivityNumber(self, sensitivity):
        """
        Returns the sensitivity number based on the provided sensitivity value.

        :param sensitivity: The sensitivity value, can be a number or one of "high", "normal", "low".
        :return: The sensitivity number.
        :raises: DetectionSensitivityNotSupportedException if the provided sensitivity value is invalid.
        """
        if sensitivity.isnumeric():
            sensitivityInt = int(sensitivity)
            if sensitivityInt >= 0 and sensitivityInt <= 100:
                return str(sensitivityInt)
            else:
                raise DetectionSensitivityNotSupportedException(
                    "Sensitivity must be between 0 and 100"
                )
        elif sensitivity == "high":
            return "80"
        elif sensitivity == "normal":
            return "50"
        elif sensitivity == "low":
            return "20"
        else:
            raise DetectionSensitivityNotSupportedException(
                "Sensitivity must be one of high, normal, low"
            )

    def setBabyCryDetection(self, enabled, sensitivity=False):
        """
        Enables or disables the baby cry detection.

        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: (Optional) The sensitivity setting. Can be one of "high", "normal", "low".
        :return: The result of the execution.
        """
        data = {"sound_detection": {"bcd": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            self.setDetectionSensitivity(sensitivity, data, "sound_detection", "bcd")
        return self.execute_function("setBCDConfig", data)

    def getBabyCryDetection(self):
        """
        Retrieves the configuration for the baby cry detection.

        :return: The baby cry detection configuration.
        """
        return self.execute_function(
            "getBCDConfig",
            {"sound_detection": {"name": ["bcd"]}},
        )["sound_detection"]["bcd"]

    def getBarkDetection(self):
        """
        Retrieves the configuration for the bark detection.

        :return: The bark detection configuration.
        """
        return self.execute_function(
            "getBarkDetectionConfig",
            {"bark_detection": {"name": ["detection"]}},
        )["bark_detection"]["detection"]

    def getMeowDetection(self):
        """
        Retrieves the configuration for the meow detection.

        :return: The meow detection configuration.
        """
        return self.execute_function(
            "getMeowDetectionConfig",
            {"meow_detection": {"name": ["detection"]}},
        )["meow_detection"]["detection"]

    def setBarkDetection(self, enabled, sensitivity=False):
        """
        Enables or disables the bark detection.

        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: (Optional) The sensitivity setting. Can be one of "high", "normal", "low".
        :return: The result of the execution.
        """
        return self.setDetectionConfiguration(
            "bark_detection", enabled, sensitivity, "setBarkDetectionConfig"
        )

    def setMeowDetection(self, enabled, sensitivity=False):
        """
        Enables or disables the meow detection.

        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: (Optional) The sensitivity setting. Can be one of "high", "normal", "low".
        :return: The result of the execution.
        """
        return self.setDetectionConfiguration(
            "meow_detection", enabled, sensitivity, "setMeowDetectionConfig"
        )

    def getGlassBreakDetection(self):
        """
        Retrieves the configuration for the glass break detection.

        :return: The glass break detection configuration.
        """
        return self.execute_function(
            "getGlassDetectionConfig",
            {"glass_detection": {"name": ["detection"]}},
        )["glass_detection"]["detection"]

    def setGlassBreakDetection(self, enabled, sensitivity=False):
        """
        Enables or disables the glass break detection.

        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: (Optional) The sensitivity setting. Can be one of "high", "normal", "low".
        :return: The result of the execution.
        """
        return self.setDetectionConfiguration(
            "glass_detection", enabled, sensitivity, "setGlassDetectionConfig"
        )

    def setDetectionConfiguration(self, configName, enabled, sensitivity, functionName):
        """
        Sets the detection configuration for the given configuration name.

        :param configName: Name of the configuration to set.
        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: The sensitivity setting. Can be one of "high", "normal", "low".
        :param functionName: The function name to be executed.
        :return: The result of the execution.
        """
        data = {configName: {"detection": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            data[configName]["detection"]["sensitivity"] = self.__getSensitivityNumber(
                sensitivity
            )
        return self.execute_function(functionName, data)

    def getTamperDetection(self):
        """
        Retrieves the configuration for the tamper detection.

        :return: The tamper detection configuration.
        """
        return self.execute_function(
            "getTamperDetectionConfig",
            {"tamper_detection": {"name": "tamper_det"}},
        )["tamper_detection"]["tamper_det"]

    def setTamperDetection(self, enabled, sensitivity=False):
        """
        Enables or disables the tamper detection.

        :param enabled: If True, enables the detection; if False, disables it.
        :param sensitivity: (Optional) The sensitivity setting. Can be one of "high", "normal", "low".
        :return: The result of the execution.
        """
        data = {
            "tamper_detection": {"tamper_det": {"enabled": "on" if enabled else "off"}}
        }
        if sensitivity:
            self.setDetectionSensitivity(
                sensitivity, data, "tamper_detection", "tamper_det"
            )
        return self.execute_function("setTamperDetectionConfig", data)

    def setDetectionSensitivity(self, sensitivity, data, configName, sensitivityKey):
        """
        Sets the sensitivity for a specific detection.

        :param sensitivity: The sensitivity setting. Can be one of "high", "normal", "low".
        :param data: The data dictionary where the configuration will be added.
        :param configName: The configuration name.
        :param sensitivityKey: The key where the sensitivity will be set.
        :raise DetectionSensitivityNotSupportedException: If the given sensitivity value is not supported.
        """
        if sensitivity not in ["high", "normal", "low"]:
            raise DetectionSensitivityNotSupportedException(
                "Sensitivity must be one of high, normal, low"
            )
        if sensitivity == "normal":
            sensitivity = "medium"
        data[configName][sensitivityKey]["sensitivity"] = sensitivity
