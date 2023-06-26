from pytapo.error import DetectionException, DetectionSensitivityNotSupportedException


class DetectionInterface:
    def __init__(self, perform_request, execute_function, childID=None):
        self.execute_function = execute_function
        self.perform_request = perform_request
        self.childID = childID

    def __getSensitivityNumber(self, sensitivity):
        """
        Converts the provided sensitivity level to a numeric value.
        Sensitivity can be provided as 'high', 'normal', 'low', or as a numeric string between '0' and '100'.

        Args:
            sensitivity (str): Sensitivity level.

        Raises:
            DetectionSensitivityNotSupportedException: If an invalid sensitivity level is provided.

        Returns:
            str: Sensitivity number.
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

    def getMotionDetection(self) -> dict:
        """
        Fetches the motion detection configuration from the camera.

        Returns:
            dict: The current motion detection configuration.
        """
        return self.execute_function(
            "getDetectionConfig",
            {"motion_detection": {"name": ["motion_det"]}},
        )["motion_detection"]["motion_det"]

    def setMotionDetection(self, enabled: bool, sensitivity=False) -> dict:
        """
        Sets the motion detection configuration on the camera.

        Args:
            enabled (bool): True if motion detection should be enabled, False otherwise.
            sensitivity (str, optional): Desired sensitivity level. Defaults to False.

        Returns:
            dict: Response from the execute function.
        """
        data = {
            "motion_detection": {"motion_det": {"enabled": "on" if enabled else "off"}},
        }
        if sensitivity:
            data["motion_detection"]["motion_det"][
                "digital_sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)
        # child devices always need digital_sensitivity setting
        if (
            self.childID
            and "digital_sensitivity" not in data["motion_detection"]["motion_det"]
        ):
            currentData = self.getMotionDetection()
            data["motion_detection"]["motion_det"]["digital_sensitivity"] = currentData[
                "digital_sensitivity"
            ]
        return self.execute_function("setDetectionConfig", data)

    def getCruise(self) -> dict:
        """
        Fetches the cruise configuration from the camera.

        Returns:
            dict: The current cruise configuration.
        """
        return self.execute_function(
            "getPatrolAction", {"patrol": {"get_patrol_action": {}}}
        )

    def setAutoTrackTarget(self, enabled: bool) -> dict:
        """
        Enables or disables auto-tracking of targets by the camera.

        Args:
            enabled (bool): True if auto-tracking should be enabled, False otherwise.

        Returns:
            dict: Response from the execute function.
        """
        return self.execute_function(
            "setTargetTrackConfig",
            {
                "target_track": {
                    "target_track_info": {"enabled": "on" if enabled else "off"}
                }
            },
        )

    def setCruise(self, enabled, coord=False) -> dict:
        """
        Enables or disables cruise mode on the camera.

        Args:
            enabled (bool): True if cruise mode should be enabled, False otherwise.
            coord (str, optional): Desired coordinate for cruise mode. Must be either 'x' or 'y'. Defaults to False.

        Raises:
            DetectionException: If an invalid coordinate is provided.

        Returns:
            dict: Response from the execute function.
        """
        if coord not in ["x", "y"] and coord is not False:
            raise DetectionException("Coord must be one of x, y")
        if enabled and coord is not False:
            return self.execute_function(
                "cruiseMove",
                {"motor": {"cruise": {"coord": coord}}},
            )
        else:
            return self.execute_function(
                "cruiseStop",
                {"motor": {"cruise_stop": {}}},
            )

    def getPersonDetection(self) -> dict:
        """
        Fetches the person detection configuration from the camera.

        Returns:
            dict: The current person detection configuration.
        """
        return self.execute_function(
            "getPersonDetectionConfig",
            {"people_detection": {"name": ["detection"]}},
        )["people_detection"]["detection"]

    def setPersonDetection(self, enabled, sensitivity=False):
        """
        Sets the person detection configuration on the camera.

        Args:
            enabled (bool): True if person detection should be enabled, False otherwise.
            sensitivity (str, optional): Desired sensitivity level. Defaults to False.

        Returns:
            dict: Response from the execute function.
        """
        return self.setDetectionConfiguration(
            "people_detection", enabled, sensitivity, "setPersonDetectionConfig"
        )

    def getVehicleDetection(self) -> dict:
        """
        Fetches the vehicle detection configuration from the camera.

        Returns:
            dict: The current vehicle detection configuration.
        """
        return self.execute_function(
            "getVehicleDetectionConfig",
            {"vehicle_detection": {"name": ["detection"]}},
        )["vehicle_detection"]["detection"]

    def setVehicleDetection(self, enabled: bool, sensitivity=False) -> dict:
        """
        Sets the vehicle detection configuration on the camera.

        Args:
            enabled (bool): True if vehicle detection should be enabled, False otherwise.
            sensitivity (str, optional): Desired sensitivity level. Defaults to False.

        Returns:
            dict: Response from the execute function.
        """
        return self.setDetectionConfiguration(
            "vehicle_detection", enabled, sensitivity, "setVehicleDetectionConfig"
        )

    def getPetDetection(self) -> dict:
        """
        Fetches the pet detection configuration from the camera.

        Returns:
            dict: The current pet detection configuration.
        """
        return self.execute_function(
            "getPetDetectionConfig",
            {"pet_detection": {"name": ["detection"]}},
        )["pet_detection"]["detection"]

    def setPetDetection(self, enabled: bool, sensitivity=False) -> dict:
        """
        Sets the pet detection configuration on the camera.

        Args:
            enabled (bool): True if pet detection should be enabled, False otherwise.
            sensitivity (str, optional): Desired sensitivity level. Defaults to False.

        Returns:
            dict: Response from the execute function.
        """
        return self.setDetectionConfiguration(
            "pet_detection", enabled, sensitivity, "setPetDetectionConfig"
        )

    def setDetectionConfiguration(
        self, detection_type, enabled, sensitivity, function_name
    ) -> dict:
        """
        Sets the detection configuration on the camera.

        This method is used to enable or disable specific types of detection (like person, vehicle, pet) and set the
        sensitivity for the detection. The type of detection and the function to execute are specified as parameters.

        Args:
            detection_type (str): The type of detection (like person, vehicle, pet).
            enabled (bool): True if the detection should be enabled, False otherwise.
            sensitivity (str): The desired sensitivity level. This can be a string numeric value between '0' and '100',
                            or one of the following string literals: 'high', 'normal', 'low'.
            function_name (str): The name of the function to execute for setting the detection configuration.

        Returns:
            dict: Response from the execute function.

        Raises:
            DetectionSensitivityNotSupportedException: If an invalid sensitivity level is provided.
        """
        data = {detection_type: {"detection": {"enabled": "on" if enabled else "off"}}}
        if sensitivity:
            data[detection_type]["detection"][
                "sensitivity"
            ] = self.__getSensitivityNumber(sensitivity)
        return self.execute_function(function_name, data)
