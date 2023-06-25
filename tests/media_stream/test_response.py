import pytest
from pytapo.media_stream.response import HttpMediaResponse


def test_http_media_response_init():
    # Initialization data
    seq = 1
    session = 1
    headers = {"Content-Type": "application/json"}
    encrypted = False
    mimetype = "application/json"
    ciphertext = None
    plaintext = b"Hello, world!"
    json_data = {"key": "value"}
    audioPayload = b"audio data"

    # Initialize HttpMediaResponse object
    response = HttpMediaResponse(
        seq,
        session,
        headers,
        encrypted,
        mimetype,
        ciphertext,
        plaintext,
        json_data,
        audioPayload,
    )

    # Assertions
    assert response.seq == seq
    assert response.session == session
    assert response.headers == headers
    assert response.encrypted == encrypted
    assert response.mimetype == mimetype
    assert response.ciphertext == ciphertext
    assert response.plaintext == plaintext
    assert response.json_data == json_data
    assert response.audioPayload == audioPayload


@pytest.mark.parametrize(
    "seq, session, mimetype",
    [
        (2, 3, "application/json"),
        (0, 0, "text/plain"),
        (123, 456, "application/octet-stream"),
    ],
)
def test_http_media_response_various_values(seq, session, mimetype):
    # Generic data
    headers = {"Content-Type": mimetype}
    encrypted = False
    ciphertext = None
    plaintext = b"Hello, world!"
    json_data = {"key": "value"}
    audioPayload = b"audio data"

    # Initialize HttpMediaResponse object
    response = HttpMediaResponse(
        seq,
        session,
        headers,
        encrypted,
        mimetype,
        ciphertext,
        plaintext,
        json_data,
        audioPayload,
    )

    # Assertions
    assert response.seq == seq
    assert response.session == session
    assert response.mimetype == mimetype
