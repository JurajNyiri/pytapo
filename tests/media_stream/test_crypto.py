import pytest
from unittest.mock import patch
from pytapo.media_stream.crypto import AESHelper
from pytapo.media_stream.error import NonceMissingException
from Crypto.Cipher import AES


@pytest.fixture
def aes_helper():
    return AESHelper(b"user", b"nonce", b"pwd", b"secret_key")


def test_init_with_nonce():
    helper = AESHelper(b"user", b"nonce", b"pwd", b"secret_key")
    assert helper.nonce == b"nonce"


def test_init_without_nonce():
    with pytest.raises(NonceMissingException):
        AESHelper(b"user", b"", b"pwd", b"secret_key")


@patch.object(AESHelper, "parse_key_exchange")
@patch.object(AESHelper, "__init__", return_value=None)
def test_from_keyexchange_and_password(mock_init, mock_parse):
    AESHelper.from_keyexchange_and_password("key_exchange", "pwd", "secret_key")
    mock_parse.assert_called_once_with("key_exchange")
    mock_init.assert_called_once()


def test_parse_key_exchange_str():
    result = AESHelper.parse_key_exchange('username="user" nonce="nonce"')
    assert result == {b"username": b"user", b"nonce": b"nonce"}


def test_parse_key_exchange_bytes():
    result = AESHelper.parse_key_exchange(b'username="user" nonce="nonce"')
    assert result == {b"username": b"user", b"nonce": b"nonce"}


@patch("Crypto.Cipher.AES.new")
def test_refresh_cipher(mock_new, aes_helper):
    aes_helper.refresh_cipher()
    mock_new.assert_called_once_with(aes_helper.key, AES.MODE_CBC, iv=aes_helper.iv)


@patch("Crypto.Cipher.AES.new")
def test_decrypt(mock_new, aes_helper):
    mock_new.return_value.decrypt.return_value = b"data"
    result = aes_helper.decrypt(b"encrypted_data")
    assert result == b"data"


@patch("Crypto.Cipher.AES.new")
def test_encrypt(mock_new, aes_helper):
    mock_new.return_value.encrypt.return_value = b"encrypted_data"
    result = aes_helper.encrypt(b"data")
    assert result == b"encrypted_data"
