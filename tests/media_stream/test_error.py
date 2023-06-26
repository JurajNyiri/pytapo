import pytest
from pytapo.error import (
    TapoException,
    ConnectionErrorException,
    HttpMediaSessionException,
    NonceMissingException,
    HttpStatusCodeException,
    TimeoutException,
)
from pytapo.media_stream.error import KeyExchangeMissingException


def raise_exception(exception):
    raise exception


def test_tapo_exception():
    with pytest.raises(TapoException):
        raise_exception(TapoException("An error occurred in the Tapo device"))


def test_connection_error_exception():
    with pytest.raises(ConnectionErrorException):
        raise_exception(ConnectionErrorException("Error connecting to the Tapo device"))


def test_http_media_session_exception():
    with pytest.raises(HttpMediaSessionException):
        raise_exception(HttpMediaSessionException("HTTP Media Session error"))


def test_nonce_missing_exception():
    with pytest.raises(NonceMissingException):
        raise_exception(NonceMissingException("Nonce is missing from key exchange"))


def test_http_status_code_exception():
    with pytest.raises(HttpStatusCodeException):
        raise_exception(HttpStatusCodeException(404))


def test_timeout_exception():
    with pytest.raises(TimeoutException):
        raise_exception(TimeoutException("Request to the Tapo device timed out"))


def test_key_exchange_missing_exception():
    with pytest.raises(KeyExchangeMissingException):
        raise_exception(
            KeyExchangeMissingException("Key exchange is missing from the Tapo device")
        )
