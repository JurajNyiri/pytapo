from pytapo.error import TapoException


class ConnectionErrorException(TapoException):
    """Exception for when there is an error connecting to the Tapo device."""

    def __init__(self, message="Error connecting to the Tapo device"):
        super().__init__(message)


class HttpMediaSessionException(TapoException):
    """Exception for HTTP media session related errors."""

    def __init__(self, message="HTTP Media Session error"):
        super().__init__(message)


class NonceMissingException(HttpMediaSessionException):
    """Exception for when nonce is missing from key exchange."""

    def __init__(self, message="Nonce is missing from key exchange"):
        super().__init__(message)


class HttpStatusCodeException(HttpMediaSessionException):
    """Exception for when HTTP request returns an error status code."""

    def __init__(self, status_code: int):
        message = f"HTTP request returned {status_code} status code"
        super().__init__(message)


class TimeoutException(TapoException):
    """Exception for when a request to the Tapo device times out."""

    def __init__(self, message="Request to the Tapo device timed out"):
        super().__init__(message)


class KeyExchangeMissingException(TapoException):
    """Exception for when key exchange is missing from the Tapo device."""

    def __init__(self, message="Key exchange is missing from the Tapo device"):
        super().__init__(message)
