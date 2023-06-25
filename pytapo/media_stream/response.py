from typing import Dict, Optional, Any

class HttpMediaResponse:
    """
    This class encapsulates the HTTP response from a media server.
    
    Attributes:
        seq (int): The sequence number of the response.
        session (int): The session identifier.
        headers (Dict[str, str]): The HTTP headers of the response.
        encrypted (bool): Indicates whether the response is encrypted.
        mimetype (str): The MIME type of the response.
        ciphertext (Optional[bytes]): The encrypted payload if present.
        plaintext (bytes): The decrypted payload.
        json_data (Any): The json data extracted from the response.
        audioPayload (bytes): The audio data extracted from the response.
    """
    
    def __init__(self,
                 seq: int,
                 session: int,
                 headers: Dict[str, str],
                 encrypted: bool,
                 mimetype: str,
                 ciphertext: Optional[bytes],
                 plaintext: bytes,
                 json_data: Any,
                 audioPayload: bytes) -> None:
        self.seq = seq
        self.session = session
        self.headers = headers
        self.encrypted = encrypted
        self.mimetype = mimetype
        self.ciphertext = ciphertext
        self.plaintext = plaintext
        self.json_data = json_data
        self.audioPayload = audioPayload
