class HttpMediaSessionException(Exception):
    pass


class NonceMissingException(HttpMediaSessionException, ValueError):
    def __init__(self) -> None:
        super().__init__("Nonce is missing from key exchange")


class HttpStatusCodeException(HttpMediaSessionException):
    def __init__(self, status_code: int) -> None:
        super().__init__("HTTP request returned {} status code".format(status_code))


class KeyExchangeMissingException(HttpMediaSessionException, RuntimeError):
    def __init__(self) -> None:
        super().__init__("Server reply does not contain the required Key-Exchange")
