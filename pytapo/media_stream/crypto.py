import hashlib
import logging
from typing import AnyStr

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from pytapo.media_stream.error import NonceMissingException

logger = logging.getLogger(__name__)


class AESHelper:
    iv = None
    key = None

    def __init__(
        self,
        username: bytes,
        nonce: bytes,
        cloud_password: bytes,
        super_secret_key: bytes,
    ):
        if not nonce:
            raise NonceMissingException()
        self.nonce = nonce

        hashed_pwd = hashlib.md5(cloud_password).hexdigest().upper().encode()
        if username == b"none":
            logger.debug(
                "Detected turned off media encryption, using super secret key."
            )
            if super_secret_key == b"":
                raise Exception(
                    "Media encryption is off and super secret key is not set."
                )
            self.key = hashlib.md5(nonce + b":" + super_secret_key).digest()
        else:
            logger.debug("Detected turned on media encryption, using cloud password.")
            self.key = hashlib.md5(nonce + b":" + hashed_pwd).digest()

        self.iv = hashlib.md5(username + b":" + nonce).digest()

        self._cipher = AES.new(self.key, AES.MODE_CBC, iv=self.iv)

        logger.debug("AES cipher set up correctly")

    @classmethod
    def from_keyexchange_and_password(
        cls, key_exchange: AnyStr, cloud_password: AnyStr, super_secret_key: AnyStr
    ):
        if type(cloud_password) == str:
            cloud_password = cloud_password.encode()
        if type(key_exchange) == str:
            key_exchange = key_exchange.encode()

        key_exchange = {
            i[0].strip().replace(b'"', b""): i[1].strip().replace(b'"', b"")
            for i in (j.split(b"=", 1) for j in key_exchange.split(b" "))
        }

        if b"nonce" not in key_exchange:
            raise NonceMissingException()

        return cls(
            key_exchange[b"username"],
            key_exchange[b"nonce"],
            cloud_password,
            super_secret_key,
        )

    def refresh(self):
        self._cipher = AES.new(self.key, AES.MODE_CBC, iv=self.iv)

    def decrypt(self, data: bytes) -> bytes:
        # Cipher IV needs to be refreshed after every decrypt
        self.refresh()
        decryptedData = unpad(self._cipher.decrypt(data), 16, style="pkcs7")
        return decryptedData

    def encrypt(self, data: bytes) -> bytes:
        # todo: maybe refresh is not needed?
        self.refresh()
        return self._cipher.encrypt(pad(data, 16, style="pkcs7"))
