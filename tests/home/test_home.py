import pytest
from unittest.mock import Mock
from pytapo.home.home import HomeAssistantInterface


@pytest.fixture
def home_assistant_interface():
    perform_request = Mock()
    execute_function = Mock()
    return HomeAssistantInterface(perform_request, execute_function)


def test_getMost(home_assistant_interface):
    response = {
        "result": {
            "responses": [
                {
                    "method": "getDeviceInfo",
                    "result": {"basic_info": "info"},
                    "error_code": 0,
                },
                {
                    "method": "getDetectionConfig",
                    "result": {"motion_det": "detected"},
                    "error_code": 0,
                },
                {
                    "method": "getPersonDetectionConfig",
                    "result": False,
                    "error_code": 1,
                },
                {"error_code": 1},
            ]
        }
    }
    home_assistant_interface.perform_request = Mock(return_value=response)
    result = home_assistant_interface.getMost()
    assert result["getDeviceInfo"] == {"basic_info": "info"}
    assert result["getDetectionConfig"] == {"motion_det": "detected"}
    assert result["getPersonDetectionConfig"] is False
    assert result["getVehicleDetectionConfig"] is False
