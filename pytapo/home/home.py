class HomeAssistantInterface:
    """Interface for HomeAssistant-Tapo-Control."""

    def __init__(self, perform_request, execute_function, child_id=None):
        """
        Initialize the HomeAssistantInterface with a function to execute API calls.

        Parameters:
        perform_request (func): The function to perform direct API calls.
        execute_function (func): The function to be used for making API requests. It should take in a function name and parameters as arguments.
        child_id (str): The ID of the child device (if applicable).
        """

        self.perform_request = perform_request
        self.execute_function = execute_function
        self.child_id = child_id

    # Used for purposes of HomeAssistant-Tapo-Control
    # Uses method names from https://md.depau.eu/s/r1Ys_oWoP
    def getMost(self):
        """Fetch a large variety of camera configurations and information.

        This method aggregates many different requests for information
        about the camera into a single API call.

        Returns:
            dict: A dictionary containing the results of each request.
                Each key is the method name, and the corresponding value
                is the result of the request or False if it was unsuccessful.
        """
        requestData = {
            "method": "multipleRequest",
            "params": {
                "requests": [
                    {
                        "method": "getDeviceInfo",
                        "params": {"device_info": {"name": ["basic_info"]}},
                    },
                    {
                        "method": "getDetectionConfig",
                        "params": {"motion_detection": {"name": ["motion_det"]}},
                    },
                    {
                        "method": "getPersonDetectionConfig",
                        "params": {"people_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getVehicleDetectionConfig",
                        "params": {"vehicle_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getBCDConfig",
                        "params": {"sound_detection": {"name": ["bcd"]}},
                    },
                    {
                        "method": "getPetDetectionConfig",
                        "params": {"pet_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getBarkDetectionConfig",
                        "params": {"bark_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getMeowDetectionConfig",
                        "params": {"meow_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getGlassDetectionConfig",
                        "params": {"glass_detection": {"name": ["detection"]}},
                    },
                    {
                        "method": "getTamperDetectionConfig",
                        "params": {"tamper_detection": {"name": "tamper_det"}},
                    },
                    {
                        "method": "getLensMaskConfig",
                        "params": {"lens_mask": {"name": ["lens_mask_info"]}},
                    },
                    {
                        "method": "getLdc",
                        "params": {"image": {"name": ["switch", "common"]}},
                    },
                    {
                        "method": "getLastAlarmInfo",
                        "params": {"msg_alarm": {"name": ["chn1_msg_alarm_info"]}},
                    },
                    {
                        "method": "getLedStatus",
                        "params": {"led": {"name": ["config"]}},
                    },
                    {
                        "method": "getTargetTrackConfig",
                        "params": {"target_track": {"name": ["target_track_info"]}},
                    },
                    {
                        "method": "getPresetConfig",
                        "params": {"preset": {"name": ["preset"]}},
                    },
                    {
                        "method": "getFirmwareUpdateStatus",
                        "params": {"cloud_config": {"name": "upgrade_status"}},
                    },
                    {
                        "method": "getMediaEncrypt",
                        "params": {"cet": {"name": ["media_encrypt"]}},
                    },
                    {
                        "method": "getConnectionType",
                        "params": {"network": {"get_connection_type": []}},
                    },
                    {"method": "getAlarmConfig", "params": {"msg_alarm": {}}},
                    {"method": "getAlarmPlan", "params": {"msg_alarm_plan": {}}},
                    {"method": "getSirenTypeList", "params": {"msg_alarm": {}}},
                    {"method": "getLightTypeList", "params": {"msg_alarm": {}}},
                    {"method": "getSirenStatus", "params": {"msg_alarm": {}}},
                    {
                        "method": "getLightFrequencyInfo",
                        "params": {"image": {"name": "common"}},
                    },
                    {
                        "method": "getLightFrequencyCapability",
                        "params": {"image": {"name": "common"}},
                    },
                    {
                        "method": "getChildDeviceList",
                        "params": {"childControl": {"start_index": 0}},
                    },
                    {
                        "method": "getRotationStatus",
                        "params": {"image": {"name": ["switch"]}},
                    },
                    {
                        "method": "getNightVisionModeConfig",
                        "params": {"image": {"name": "switch"}},
                    },
                ]
            },
        }
        results = self.perform_request(requestData)

        returnData = {}
        for i, result in enumerate(results["result"]["responses"]):
            if (
                "error_code" in result and result["error_code"] == 0
            ) and "result" in result:
                returnData[result["method"]] = result["result"]
            elif "method" in result:
                returnData[result["method"]] = False
            else:  # some cameras are not returning method for error messages
                returnData[requestData["params"]["requests"][i]["method"]] = False
        return returnData
