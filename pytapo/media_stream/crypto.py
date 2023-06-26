import hashlib
import logging
from typing import AnyStr, Dict, Optional

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from pytapo.media_stream.error import NonceMissingException

logger = logging.getLogger(__name__)

class AESHelper:
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
        self.key = hashlib.md5(nonce + b":" + (super_secret_key if username == b"none" else hashed_pwd)).digest()
        self.iv = hashlib.md5(username + b":" + nonce).digest()
        self._cipher = AES.new(self.key, AES.MODE_CBC, iv=self.iv)

        logger.debug("AES cipher set up correctly")

    @classmethod
    def from_keyexchange_and_password(
        cls, key_exchange: AnyStr, cloud_password: AnyStr, super_secret_key: AnyStr
    ) -> 'AESHelper':
        key_exchange = cls.parse_key_exchange(key_exchange)
        return cls(key_exchange[b"username"], key_exchange[b"nonce"], cloud_password.encode(), super_secret_key)

    @staticmethod
    def parse_key_exchange(key_exchange: AnyStr) -> Dict[bytes, bytes]:
        if isinstance(key_exchange, str):
            key_exchange = key_exchange.encode()
        return {i[0].strip().replace(b'"', b""): i[1].strip().replace(b'"', b"") for i in (j.split(b"=", 1) for j in key_exchange.split(b" "))}

    def refresh_cipher(self):
        self._cipher = AES.new(self.key, AES.MODE_CBC, iv=self.iv)

    def decrypt(self, data: bytes) -> bytes:
        self.refresh_cipher()
        return unpad(self._cipher.decrypt(data), 16, style="pkcs7")

    def encrypt(self, data: bytes) -> bytes:
        self.refresh_cipher()
        return self._cipher.encrypt(pad(data, 16, style="pkcs7"))
