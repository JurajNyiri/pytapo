from typing import Mapping, Optional


class HttpMediaResponse:
    def __init__(
        self,
        seq: Optional[int],
        session: Optional[int],
        headers: Mapping[str, str],
        encrypted: bool,
        mimetype: str,
        ciphertext: Optional[bytes],
        plaintext: bytes,
        audioPayload: bytes,
        json_data,
    ):
        self.seq = seq
        self.session = session
        self.headers = headers
        self.encrypted = encrypted
        self.mimetype = mimetype
        self.ciphertext = ciphertext
        self.plaintext = plaintext
        self.json_data = json_data
        self.audioPayload = audioPayload
