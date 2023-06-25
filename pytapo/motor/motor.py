from datetime import datetime
from warnings import warn
from pytapo.error import (
    DayNightModeNotSupportedException,
    ImageCommonNotSupportedException,
    MotorException,
    RecordingNotSupportedException,
)


class MotorInterface:
    def __init__(self, perform_request, execute_function, child_id=None):

        """
        Initializes a new Motor instance.
        Parameters:
        child_id (str, optional): The child camera identifier.
        """
        self.child_id = child_id
        self.perform_request = perform_request
        self.execute_function = execute_function

    def move_motor(self, x, y):
        """
        Moves the camera's motor to the specified coordinates.

        Parameters:
        x (int): The x-coordinate to move the motor to.
        y (int): The y-coordinate to move the motor to.

        Returns:
        dict: The response from the camera.
        """
        return self.perform_request(
            {"method": "do", "motor": {"move": {"x_coord": str(x), "y_coord": str(y)}}}
        )

    def move_motor_step(self, angle):
        """
        Moves the camera's motor a certain angle.

        Parameters:
        angle (int): The angle in degrees to move the motor. Must be between 0 and 360.

        Returns:
        dict: The response from the camera.
        """
        if not (0 <= angle < 360):
            raise MotorException("Angle must be in a range 0 <= angle < 360")
        return self.perform_request(
            {"method": "do", "motor": {"movestep": {"direction": str(angle)}}}
        )

    def move_motor_clockwise(self):
        """
        Moves the camera's motor clockwise.

        Returns:
        dict: The response from the camera.
        """
        return self.move_motor_step(0)

    def move_motor_counterclockwise(self):
        """
        Moves the camera's motor counterclockwise.

        Returns:
        dict: The response from the camera.
        """
        return self.move_motor_step(180)

    def move_motor_vertical(self):
        """
        Moves the camera's motor vertically.

        Returns:
        dict: The response from the camera.
        """
        return self.move_motor_step(90)

    def move_motor_horizontal(self):
        """
        Moves the camera's motor horizontally.

        Returns:
        dict: The response from the camera.
        """
        return self.move_motor_step(270)

    def calibrate_motor(self):
        """
        Calibrates the camera's motor.

        Returns:
        dict: The response from the camera.
        """
        return self.perform_request({"method": "do", "motor": {"manual_cali": ""}})

    def get_motor_capability(self):
        """
        Retrieves the capabilities of the camera's motor.

        Returns:
        dict: The capabilities of the motor.
        """
        return self.perform_request(
            {"method": "get", "motor": {"name": ["capability"]}}
        )
