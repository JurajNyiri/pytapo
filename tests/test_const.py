import pytest

from pytapo.const import ERROR_CODES
from pytapo.error import TapoException


def test_error_codes():
    expected_messages = {
        "-40401": "Invalid stok value",
        "-40210": "Function not supported",
        "-64303": "Action cannot be done while camera is in patrol mode.",
        "-64324": "Privacy mode is ON, not able to execute",
        "-64302": "Preset ID not found",
        "-64321": "Preset ID was deleted so no longer exists",
        "-40106": "Parameter to get/do does not exist",
        "-40105": "Method does not exist",
        "-40101": "Parameter to set does not exist",
        "-40209": "Invalid login credentials",
        "-64304": "Maximum Pan/Tilt range reached",
    }
    for error_code, expected_message in expected_messages.items():
            assert ERROR_CODES[error_code] == expected_message
