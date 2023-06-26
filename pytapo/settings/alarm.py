from pytapo.error import AlarmException


class AlarmInterface:
    """
    An interface for interacting with alarm settings on a Tapo device.
    """

    def __init__(self, execute_function, perform_request, child_id):
        """
        Initialize the AlarmInterface with functions to execute API calls and device's child ID.

        Parameters:
        execute_function (func): The function to be used for making API requests.
        perform_request (func): The function to perform direct API calls.
        child_id (str): The ID of the child device (if applicable).
        """
        self.execute = execute_function
        self.perform_request = perform_request
        self.child_id = child_id

    def _manual_alarm(self, action):
        """
        Function to start or stop manual alarm. This does not work for child devices.

        Parameters:
        action (str): The action to perform. Can be "start" or "stop".

        Returns:
        dict: The result of the operation.
        """
        return self.perform_request(
            {
                "method": "do",
                "msg_alarm": {"manual_msg_alarm": {"action": action}},
            }
        )

    def start_manual_alarm(self):
        return self._manual_alarm("start")

    def stop_manual_alarm(self):
        return self._manual_alarm("stop")

    def set_alarm(self, enabled, sound_enabled=True, light_enabled=True):
        """
        Sets the alarm configuration. At least one of sound or light must be enabled.

        Parameters:
        enabled (bool): Whether the alarm is enabled.
        sound_enabled (bool): Whether sound is enabled.
        light_enabled (bool): Whether light is enabled.

        Returns:
        dict: The result of the set operation.

        Raises:
        Exception: If neither sound nor light is enabled.
        """
        if not sound_enabled and not light_enabled:
            raise AlarmException("At least one of sound or light must be enabled")

        alarm_mode = [
            item
            for condition, item in [
                (sound_enabled, "siren" if self.child_id else "sound"),
                (light_enabled, "light"),
            ]
            if condition
        ]

        msg_alarm = {
            "enabled": "on" if enabled else "off",
            "alarm_mode": alarm_mode,
        }
        if self.child_id:
            return self.execute("setAlarmConfig", {"msg_alarm": msg_alarm})
        else:
            return self.perform_request(
                {
                    "method": "set",
                    "msg_alarm": {
                        "chn1_msg_alarm_info": {
                            **msg_alarm,
                            "alarm_type": "0",
                            "light_type": "0",
                        }
                    },
                }
            )

    def get_alarm(self):
        """
        Retrieves the last alarm information or the current alarm configuration based on whether the device is a child.

        Returns:
        dict: Alarm information or configuration.
        """
        if not self.child_id:
            return self.execute(
                "getLastAlarmInfo",
                {"msg_alarm": {"name": ["chn1_msg_alarm_info"]}},
            )["msg_alarm"]["chn1_msg_alarm_info"]

        data = self.get_alarm_config()

        # replace "siren" with "sound", some cameras call it siren, some sound
        for i in range(len(data[0]["result"]["alarm_mode"])):
            if data[0]["result"]["alarm_mode"][i] == "siren":
                data[0]["result"]["alarm_mode"][i] = "sound"
        return {
            "alarm_type": "0",
            "light_type": "0",
            "enabled": data[0]["result"]["enabled"],
            "alarm_mode": data[0]["result"]["alarm_mode"],
        }

    def get_alarm_config(self):
        """
        Requests multiple alarm-related configurations from the device.

        Returns:
        dict: The requested alarm configurations.
        """
        return self.execute(
            "multipleRequest",
            {
                "requests": [
                    {"method": method, "params": {f"msg_{method.lower()}": {}}}
                    for method in [
                        "getAlarmConfig",
                        "getAlarmPlan",
                        "getSirenTypeList",
                        "getLightTypeList",
                        "getSirenStatus",
                    ]
                ]
            },
        )
