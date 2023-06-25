import pytest
import asyncio
from unittest.mock import MagicMock, patch
from pytapo.media_stream.session import HttpMediaSession


@pytest.mark.asyncio
async def test_send():
    # Mocking necessary methods and properties
    with patch.object(
        HttpMediaSession, "_send_http_request", return_value=None
    ), patch.object(HttpMediaSession, "_writer", new_callable=MagicMock), patch.object(
        HttpMediaSession, "_aes", new_callable=MagicMock
    ):
        # Instantiate your class
        obj = HttpMediaSession()

        # Create necessary mock objects for parameters
        data = "test_data"
        mimetype = "application/json"
        HttpMediaSession = 1
        sequence = 2
        no_data_timeout = 3
        encrypt = False

        # Set necessary properties
        obj._started = True
        obj._HttpMediaSessions = {HttpMediaSession: asyncio.Queue()}
        obj._sequence_numbers = {sequence: asyncio.Queue()}
        obj.client_boundary = "client_boundary"
        obj.window_size = 2

        # Call the send method
        result = obj.send(
            data, mimetype, HttpMediaSession, sequence, no_data_timeout, encrypt
        )

        # Assertions
        obj._send_http_request.assert_called()
        obj._writer.write.assert_called()
        obj._writer.drain.assert_called()
