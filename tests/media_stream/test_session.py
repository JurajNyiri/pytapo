import pytest
import asyncio
from unittest.mock import MagicMock, patch
from pytapo.media_stream.session import HttpMediaSession


@pytest.mark.asyncio
async def test_start_session():
    # Instantiate your class
    obj = HttpMediaSession("localhost", "", "")
    obj._writer = MagicMock()

    with patch(
        "asyncio.open_connection", return_value=(MagicMock(), MagicMock())
    ) as mock_open_connection:
        await obj.start()
        mock_open_connection.assert_called()


@pytest.mark.asyncio
async def test_close_session():
    # Instantiate your class
    obj = HttpMediaSession("localhost", "", "")
    obj._writer = MagicMock()

    with patch(
        "asyncio.open_connection", return_value=(MagicMock(), MagicMock())
    ) as mock_open_connection:
        await obj.start()
        await obj.close()
        mock_open_connection.assert_called()


@pytest.mark.asyncio
async def test_send_data():
    # Instantiate your class
    obj = HttpMediaSession("localhost", "", "")
    obj._writer = MagicMock()

    # Mocking necessary methods and properties
    with patch.object(
        obj, "_send_http_request", return_value=None
    ) as mock_request, patch.object(obj, "_aes", new_callable=MagicMock) as mock_aes:
        # Create necessary mock objects for parameters
        data = "test_data"
        mimetype = "application/json"
        media_session = 1
        sequence = 2
        no_data_timeout = 3
        encrypt = False

        # Set necessary properties
        obj._started = True
        obj._sessions = {media_session: asyncio.Queue()}
        obj._sequence_numbers = {sequence: asyncio.Queue()}
        obj.client_boundary = "client_boundary"
        obj.window_size = 2

        # Call the send method
        async for _ in obj.transceive(
            data, mimetype, media_session, sequence, no_data_timeout, encrypt
        ):
            pass

        # Assertions
        mock_request.assert_called()
        mock_aes.encrypt.assert_called_with(data)
        assert obj._writer.write.call_count == 2  # data + newline
        assert obj._writer.drain.call_count == 3  # 2x data + newline
