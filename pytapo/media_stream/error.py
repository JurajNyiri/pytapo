class TapoException(Exception):
    """Base exception class for all exceptions related to the Tapo class."""

    def __init__(self, message="An error occurred in the Tapo device"):
        super().__init__(message)


class ConnectionErrorException(TapoException):
    """Exception for when there is an error connecting to the Tapo device."""

    def __init__(self, message="Error connecting to the Tapo device"):
        super().__init__(message)


class DeviceNotFoundException(TapoException):
    """Exception for when the Tapo device could not be found."""

    def __init__(self, message="The Tapo device could not be found"):
        super().__init__(message)


class FirmwareUpdateNotAvailableException(TapoException):
    """Exception for when there is no firmware update available."""

    def __init__(self, message="No firmware update available"):
        super().__init__(message)


class HttpMediaSessionException(TapoException):
    """Exception for HTTP media session related errors."""

    def __init__(self, message="HTTP Media Session error"):
        super().__init__(message)


class ImageCommonNotSupportedException(TapoException):
    """Exception for when an operation related to image common is not supported by the Tapo device."""

    def __init__(self, message="Image common operation not supported"):
        super().__init__(message)


class InvalidCredentialsException(TapoException):
    """Exception for when the provided credentials are invalid."""

    def __init__(self, message="Provided credentials are invalid"):
        super().__init__(message)


class InvalidModeException(TapoException):
    """Exception for when an invalid mode is set for a certain operation."""

    def __init__(self, message="Invalid mode set for operation"):
        super().__init__(message)


class KeyExchangeMissingException(HttpMediaSessionException):
    """Exception for when the required Key-Exchange is missing."""

    def __init__(
        self, message="Server reply does not contain the required Key-Exchange"
    ):
        super().__init__(message)


class NonceMissingException(HttpMediaSessionException):
    """Exception for when nonce is missing from key exchange."""

    def __init__(self, message="Nonce is missing from key exchange"):
        super().__init__(message)


class PresetNotFoundException(TapoException):
    """Exception for when a preset could not be found on the Tapo device."""

    def __init__(self, message="Preset not found on the Tapo device"):
        super().__init__(message)


class HttpStatusCodeException(HttpMediaSessionException):
    """Exception for when HTTP request returns an error status code."""

    def __init__(self, status_code: int):
        message = f"HTTP request returned {status_code} status code"
        super().__init__(message)


class SwitchNotSupportedException(TapoException):
    """Exception for when a requested switch is not supported by the Tapo device."""

    def __init__(self, message="Requested switch is not supported by the Tapo device"):
        super().__init__(message)


class TimeoutException(TapoException):
    """Exception for when a request to the Tapo device times out."""

    def __init__(self, message="Request to the Tapo device timed out"):
        super().__init__(message)


class UnauthorizedException(TapoException):
    """Exception for when the client is unauthorized to perform a certain action."""

    def __init__(self, message="Client is unauthorized to perform this action"):
        super().__init__(message)


class UnsupportedOperationException(TapoException):
    """Exception for when the requested operation is not supported by the Tapo device."""

    def __init__(
        self, message="Requested operation is not supported by the Tapo device"
    ):
        super().__init__(message)
