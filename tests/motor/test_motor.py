import pytest
from unittest.mock import Mock
from pytapo.error import MotorException
from pytapo.motor.motor import MotorInterface


@pytest.fixture
def motor_interface():
    perform_request = Mock()
    execute_function = Mock()
    return MotorInterface(perform_request, execute_function)


def test_move_motor(motor_interface):
    motor_interface.move_motor(1, 1)
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"move": {"x_coord": "1", "y_coord": "1"}}}
    )


def test_move_motor_step(motor_interface):
    motor_interface.move_motor_step(90)
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"movestep": {"direction": "90"}}}
    )


def test_move_motor_step_exception(motor_interface):
    with pytest.raises(MotorException):
        motor_interface.move_motor_step(360)


def test_move_motor_clockwise(motor_interface):
    motor_interface.move_motor_clockwise()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"movestep": {"direction": "0"}}}
    )


def test_move_motor_counterclockwise(motor_interface):
    motor_interface.move_motor_counterclockwise()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"movestep": {"direction": "180"}}}
    )


def test_move_motor_vertical(motor_interface):
    motor_interface.move_motor_vertical()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"movestep": {"direction": "90"}}}
    )


def test_move_motor_horizontal(motor_interface):
    motor_interface.move_motor_horizontal()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"movestep": {"direction": "270"}}}
    )


def test_calibrate_motor(motor_interface):
    motor_interface.calibrate_motor()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "do", "motor": {"manual_cali": ""}}
    )


def test_get_motor_capability(motor_interface):
    motor_interface.get_motor_capability()
    motor_interface.perform_request.assert_called_once_with(
        {"method": "get", "motor": {"name": ["capability"]}}
    )
