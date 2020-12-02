import hashlib
import logging
from typing import AnyStr

from Crypto.Cipher import AES

from pytapo.media_stream.error import NonceMissingException

logger = logging.getLogger(__name__)


class AESHelper:

    def __init__(self, username: bytes, nonce: bytes, cloud_password: bytes):
        if not nonce:
            raise NonceMissingException()
        self.nonce = nonce

        key = hashlib.md5(nonce + b":" + cloud_password).digest()
        iv = hashlib.md5(username + b":" + nonce).digest()
        self._cipher = AES.new(key, AES.MODE_CBC, iv)

        logger.debug("AES cipher set up correctly")

    @classmethod
    def from_keyexchange_and_password(cls, key_exchange: AnyStr, cloud_password: AnyStr):
        if type(cloud_password) == str:
            cloud_password = cloud_password.encode()
        if type(key_exchange) == str:
            key_exchange = key_exchange.encode()

        key_exchange = {
            i[0].strip().replace(b'"', b''): i[1].strip().replace(b'"', b'')
            for i in (j.split(b"=", 1) for j in key_exchange.split(b" "))
        }

        if b"nonce" not in key_exchange:
            raise NonceMissingException()

        return cls(key_exchange[b"username"], key_exchange[b"nonce"], cloud_password)

    def decrypt(self, data: bytes) -> bytes:
        return self._cipher.decrypt(data)

    def encrypt(self, data: bytes) -> bytes:
        return self._cipher.encrypt(data)
