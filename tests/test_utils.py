import pytest
from pytapo.const import ERROR_CODES
from pytapo.utils import getErrorMessage


def test_get_error_message():
    # Test that each error code returns the correct message
    for error_code, expected_message in ERROR_CODES.items():
        assert getErrorMessage(error_code) == str(expected_message)

    # Test that an unknown error code returns its own value as a string
    unknown_error_code = -99999
    assert getErrorMessage(unknown_error_code) == str(unknown_error_code)
