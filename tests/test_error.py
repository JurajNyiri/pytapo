import pytest
from pytapo.error import (
    TapoException,
    ConnectionErrorException,
    DeviceNotFoundException,
    FirmwareUpdateNotAvailableException,
    HttpMediaSessionException,
    ImageCommonNotSupportedException,
    InvalidCredentialsException,
    InvalidModeException,
    KeyExchangeMissingException,
    NonceMissingException,
    PresetNotFoundException,
    HttpStatusCodeException,
    SwitchNotSupportedException,
    TimeoutException,
    UnauthorizedException,
    UnsupportedOperationException,
    DayNightModeNotSupportedException,
    DetectionSensitivityNotSupportedException,
    DetectionException,
    RecordingNotSupportedException,
    LightFrequencyModeNotSupportedException,
    AuthInvalidException,
    AlarmException,
    MotorException,
    ResponseException,
    SettingsException
)


def test_exceptions():
    exception_classes = [
        (TapoException, "An error occurred in the Tapo device"),
        (ConnectionErrorException, "Error connecting to the Tapo device"),
        (DeviceNotFoundException, "The Tapo device could not be found"),
        (FirmwareUpdateNotAvailableException, "No firmware update available"),
        (HttpMediaSessionException, "HTTP Media Session error"),
        (ImageCommonNotSupportedException, "Image common operation not supported"),
        (InvalidCredentialsException, "Provided credentials are invalid"),
        (InvalidModeException, "Invalid mode set for operation"),
        (
            KeyExchangeMissingException,
            "Server reply does not contain the required Key-Exchange",
        ),
        (NonceMissingException, "Nonce is missing from key exchange"),
        (PresetNotFoundException, "Preset not found on the Tapo device"),
        (HttpStatusCodeException, "HTTP request returned {} status code"),
        (
            SwitchNotSupportedException,
            "Requested switch is not supported by the Tapo device",
        ),
        (TimeoutException, "Request to the Tapo device timed out"),
        (UnauthorizedException, "Client is unauthorized to perform this action"),
        (
            UnsupportedOperationException,
            "Requested operation is not supported by the Tapo device",
        ),
        (
            DayNightModeNotSupportedException,
            "Requested day night mode is not supported by the Tapo device",
        ),
        (
            DetectionSensitivityNotSupportedException,
            "Requested detection sensitivity is not supported by the Tapo device",
        ),
        (DetectionException, "Requested detection is not supported by the Tapo device"),
        (
            RecordingNotSupportedException,
            "Requested recording is not supported by the Tapo device",
        ),
        (
            LightFrequencyModeNotSupportedException,
            "Requested light frequency mode is not supported by the Tapo device",
        ),
        (AuthInvalidException, "Auth invalid"),
        (AlarmException, "Alarm exception"),
        (MotorException, "Motor exception"),
        (ResponseException, "Response exception"),
        (SettingsException, "Settings exception"),
    ]

    for exception_class, expected_message in exception_classes:
        with pytest.raises(exception_class) as exc_info:
            if exception_class is HttpStatusCodeException:
                raise exception_class(500)
            else:
                raise exception_class()

        assert str(exc_info.value) == expected_message
