import asyncio
import hashlib
import json
import logging
import random
import warnings
from asyncio import StreamReader, StreamWriter, Task, Queue
from json import JSONDecodeError
from typing import Optional, Mapping, Generator, MutableMapping

from rtp import PayloadType

from pytapo.media_stream._utils import (
    generate_nonce,
    md5digest,
    parse_http_response,
    parse_http_headers,
)
from pytapo.media_stream.crypto import AESHelper
from pytapo.media_stream.error import (
    HttpStatusCodeException,
    KeyExchangeMissingException,
)
from pytapo.media_stream.response import HttpMediaResponse
from pytapo.media_stream.tsReader import TSReader

logger = logging.getLogger(__name__)


class HttpMediaSession:
    def __init__(
        self,
        ip: str,
        cloud_password: str,
        super_secret_key: str,
        window_size=500,  # 500 is a sweet point for download speed
        port: int = 8800,
        username: str = "admin",
        multipart_boundary: bytes = b"--client-stream-boundary--",
    ):
        self.ip = ip
        self.window_size = window_size
        self.cloud_password = cloud_password
        self.super_secret_key = super_secret_key
        self.hashed_password = md5digest(cloud_password.encode()).decode()
        self.port = port
        self.username = username
        self.client_boundary = multipart_boundary

        self._started: bool = False
        self._response_handler_task: Optional[Task] = None

        self._auth_data: Mapping[str, str] = {}
        self._authorization: Optional[str] = None
        self._device_boundary = b"--device-stream-boundary--"
        self._key_exchange: Optional[str] = None
        self._aes: Optional[AESHelper] = None

        # Socket stream pair
        self._reader: Optional[StreamReader] = None
        self._writer: Optional[StreamWriter] = None

        self._sequence_numbers: MutableMapping[int, Queue] = {}
        self._sessions: MutableMapping[int, Queue] = {}

    def set_window_size(self, window_size):
        self.window_size = window_size

    @property
    def started(self) -> bool:
        return self._started

    async def __aenter__(self):
        await self.start()
        return self

    async def start(self):
        req_line = b"POST /stream HTTP/1.1"
        headers = {
            b"Content-Type": "multipart/mixed;boundary={}".format(
                self.client_boundary.decode()
            ).encode(),
            b"Connection": b"keep-alive",
            b"Content-Length": b"-1",
        }
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.ip, self.port
            )
            logger.info("Connected to the media streaming server")

            # Step one: perform unauthenticated request
            await self._send_http_request(req_line, headers)

            data = await self._reader.readuntil(b"\r\n\r\n")
            res_line, headers_block = data.split(b"\r\n", 1)
            _, status_code, _ = parse_http_response(res_line)
            res_headers = parse_http_headers(headers_block)

            self._auth_data = {
                i[0].strip().replace('"', ""): i[1].strip().replace('"', "")
                for i in (
                    j.split("=")
                    for j in res_headers["WWW-Authenticate"].split(" ", 1)[1].split(",")
                )
            }
            self._auth_data.update(
                {
                    "username": self.username,
                    "cnonce": generate_nonce(24).decode(),
                    "nc": "00000001",
                    "qop": "auth",
                }
            )

            challenge1 = hashlib.md5(
                ":".join(
                    (self.username, self._auth_data["realm"], self.hashed_password)
                ).encode()
            ).hexdigest()
            challenge2 = hashlib.md5(b"POST:/stream").hexdigest()

            self._auth_data["response"] = hashlib.md5(
                b":".join(
                    (
                        challenge1.encode(),
                        self._auth_data["nonce"].encode(),
                        self._auth_data["nc"].encode(),
                        self._auth_data["cnonce"].encode(),
                        self._auth_data["qop"].encode(),
                        challenge2.encode(),
                    )
                )
            ).hexdigest()

            self._authorization = (
                'Digest username="{username}",realm="{realm}"'
                ',uri="/stream",algorithm=MD5,'
                'nonce="{nonce}",nc={nc},cnonce="{cnonce}",qop={qop},'
                'response="{response}",opaque="{opaque}"'.format(
                    **self._auth_data
                ).encode()
            )
            headers[b"Authorization"] = self._authorization

            logger.debug("Authentication data retrieved")

            # Step two: start actual communication
            await self._send_http_request(req_line, headers)

            # Ensure the request was successful
            data = await self._reader.readuntil(b"\r\n\r\n")
            res_line, headers_block = data.split(b"\r\n", 1)
            _, status_code, _ = parse_http_response(res_line)
            if status_code != 200:
                raise HttpStatusCodeException(status_code)

            # Parse important HTTP headers
            res_headers = parse_http_headers(headers_block)
            if "Key-Exchange" not in res_headers:
                raise KeyExchangeMissingException

            boundary = None
            if "Content-Type" in res_headers:
                # noinspection PyBroadException
                try:
                    boundary = filter(
                        lambda chunk: chunk.startswith("boundary="),
                        res_headers["Content-Type"].split(";"),
                    ).__next__()
                    boundary = boundary.split("=")[1].encode()
                except Exception:
                    boundary = None
            if not boundary:
                warnings.warn(
                    "Server did not provide a multipart/mixed boundary."
                    + " Assuming default."
                )
            else:
                self._device_boundary = boundary

            # Prepare for AES decryption of content
            self._key_exchange = res_headers["Key-Exchange"]
            self._aes = AESHelper.from_keyexchange_and_password(
                self._key_exchange.encode(),
                self.cloud_password.encode(),
                self.super_secret_key.encode(),
            )

            logger.debug("AES key exchange performed")

            # Start the response handler in the background to shuffle
            # responses to the correct callers
            self._started = True
            self._response_handler_task = asyncio.create_task(
                self._device_response_handler_loop()
            )

        except Exception:
            # Close socket in case of issues during setup
            # noinspection PyBroadException
            try:
                self._writer.close()
            except Exception:
                pass
            self._started = False
            raise

    async def _send_http_request(
        self, delimiter: bytes, headers: Mapping[bytes, bytes]
    ):
        self._writer.write(delimiter + b"\r\n")
        for header, value in headers.items():
            self._writer.write(b": ".join((header, value)) + b"\r\n")
            await self._writer.drain()

        self._writer.write(b"\r\n")
        await self._writer.drain()

    async def _device_response_handler_loop(self):
        logger.debug("Response handler is running")

        while self._started:
            session = None
            seq = None

            # We're only interested in what comes after it,
            # what's before and the boundary goes to the trash
            await self._reader.readuntil(self._device_boundary)

            logger.debug("Handling new server response")

            # print("got response")

            # Read and parse headers
            headers_block = await self._reader.readuntil(b"\r\n\r\n")
            headers = parse_http_headers(headers_block)
            # print(headers)

            mimetype = headers["Content-Type"]
            length = int(headers["Content-Length"])
            encrypted = bool(int(headers["X-If-Encrypt"]))

            if "X-Session-Id" in headers:
                session = int(headers["X-Session-Id"])
            if "X-Data-Sequence" in headers:
                seq = int(headers["X-Data-Sequence"])

            # print(headers)

            # Now we know the content length, let's read it and decrypt it
            json_data = None
            # print("TEST0")
            data = await self._reader.readexactly(length)
            if encrypted:
                # print("encrypted")
                ciphertext = data
                # print("TEST1")
                try:
                    # print("lolo")
                    # print(ciphertext)
                    plaintext = self._aes.decrypt(ciphertext)
                    # if length == 384:
                    # print(plaintext)
                    # print("lala")
                    # print(plaintext)
                except ValueError as e:
                    # print(e)
                    if "padding is incorrect" in e.args[0].lower():
                        e = ValueError(
                            e.args[0]
                            + " - This usually means that"
                            + " the cloud password is incorrect."
                        )
                    plaintext = e
                except Exception as e:
                    plaintext = e
            else:
                # print("plaintext")
                ciphertext = None
                plaintext = data
            # print(plaintext)
            # JSON responses sometimes have the above info in the payload,
            # not the headers. Let's parse it.
            if mimetype == "application/json":
                try:
                    json_data = json.loads(plaintext.decode())
                    if "seq" in json_data:
                        # print("Setting seq")
                        seq = json_data["seq"]
                    if "params" in json_data and "session_id" in json_data["params"]:
                        session = int(json_data["params"]["session_id"])
                        # print("Setting session")
                except JSONDecodeError:
                    logger.warning("Unable to parse JSON sent from device")

            if (
                (session is None)
                and (seq is None)
                or (
                    (session is not None)
                    and (session not in self._sessions)
                    and (seq is not None)
                    and (seq not in self._sequence_numbers)
                )
            ):
                logger.warning(
                    "Received response with no or invalid session information "
                    "(sequence {}, session {}), can't be delivered".format(seq, session)
                )
                continue

            # # Update our own sequence numbers to avoid collisions
            # if (seq is not None) and (seq > self._seq_counter):
            #     self._seq_counter = seq + 1

            queue: Optional[Queue] = None

            # Move queue to use sessions from now on
            if (
                (session is not None)
                and (seq is not None)
                and (session not in self._sessions)
                and (seq in self._sequence_numbers)
            ):
                queue = self._sequence_numbers.pop(seq)
                self._sessions[session] = queue
            elif (session is not None) and (session in self._sessions):
                queue = self._sessions[session]

            if queue is None:
                raise AssertionError("BUG! Queue not retrieved and not caught earlier")

            response_obj = HttpMediaResponse(
                seq=seq,
                session=session,
                headers=headers,
                encrypted=encrypted,
                mimetype=mimetype,
                ciphertext=ciphertext,
                plaintext=plaintext,
                json_data=json_data,
                audioPayload=b"",
            )

            if seq is not None and seq % self.window_size == 0:  # never ack live stream
                # print("sending ack")
                data = {
                    "type": "notification",
                    "params": {"event_type": "stream_sequence"},
                }
                data = json.dumps(data, separators=(",", ":")).encode()
                headers = {}
                headers[b"X-Session-Id"] = str(session).encode()
                headers[b"X-Data-Received"] = str(
                    self.window_size * (seq // self.window_size)
                ).encode()
                headers[b"Content-Length"] = str(len(data)).encode()
                logger.debug("Sending acknowledgement...")

                await self._send_http_request(b"--" + self.client_boundary, headers)
                chunk_size = 4096
                for i in range(0, len(data), chunk_size):
                    # print(data[i : i + chunk_size])
                    self._writer.write(data[i : i + chunk_size])
                    await self._writer.drain()

            logger.debug(
                (
                    "{} response of type {} processed (sequence {}, session {})"
                    ", dispatching to queue {}"
                ).format(
                    "Encrypted" if encrypted else "Plaintext",
                    mimetype,
                    seq,
                    session,
                    id(queue),
                )
            )

            await queue.put(response_obj)

    async def transceive(
        self,
        data: str,
        mimetype: str = "application/json",
        session: int = None,
        encrypt: bool = False,
        no_data_timeout=10.0,
    ) -> Generator[HttpMediaResponse, None, None]:
        sequence = None
        queue = None
        tsReader = TSReader()

        if mimetype != "application/json" and session is None:
            raise ValueError("Non-JSON streams must always be bound to a session")

        if mimetype == "application/json":
            j = json.loads(data)
            if "type" in j and j["type"] == "request":
                # Use random high sequence number to avoid collisions
                # with sequence numbers from server in queue

                # dispatching
                sequence = random.randint(1000, 0x7FFF)
                j["seq"] = sequence
            data = json.dumps(j, separators=(",", ":"))

        if (
            (sequence is None)
            and (session is None)
            or (session is not None and session not in self._sessions)
        ):
            raise ValueError(
                "Data is not a request and no existing session has been found"
            )

        if session is not None:
            queue = self._sessions[session]
        if sequence is not None:
            queue = asyncio.Queue(128)
            self._sequence_numbers[sequence] = queue

        if type(data) == str:
            data = data.encode()

        headers = {
            b"Content-Type": mimetype.encode(),
        }

        if encrypt:
            data = self._aes.encrypt(data)
            headers[b"X-If-Encrypt"] = b"1"

        headers[b"Content-Length"] = str(len(data)).encode()

        if mimetype != "application/json":
            headers[b"X-If-Encrypt"] = str(
                int(encrypt)
            ).encode()  # Always sent if data is not JSON
            if session is not None:
                headers[b"X-Session-Id"] = str(
                    session
                ).encode()  # If JSON, session is included in the payload

        if self.window_size is not None:
            headers[b"X-Data-Window-Size"] = str(self.window_size).encode()

        await self._send_http_request(b"--" + self.client_boundary, headers)

        chunk_size = 4096
        # print("Sending:")
        for i in range(0, len(data), chunk_size):
            # print(data[i : i + chunk_size])
            self._writer.write(data[i : i + chunk_size])
            await self._writer.drain()

        self._writer.write(b"\r\n")
        await self._writer.drain()

        logger.debug(
            (
                "{} request of type {} sent (sequence {}, session {})"
                ", expecting {} responses from queue {}"
            ).format(
                "Encrypted" if encrypt else "Plaintext",
                mimetype,
                sequence,
                session,
                self.window_size + 1,
                id(queue),
            )
        )

        try:
            while True:
                coro = queue.get()
                if no_data_timeout is not None:
                    try:
                        resp: HttpMediaResponse = await asyncio.wait_for(
                            coro, timeout=no_data_timeout
                        )
                    except asyncio.exceptions.TimeoutError:
                        print(
                            "Server did not send a new chunk in {} sec (sequence {}"
                            ", session {}), assuming the stream is over".format(
                                no_data_timeout, sequence, session
                            )
                        )
                        logger.debug(
                            "Server did not send a new chunk in {} sec (sequence {}"
                            ", session {}), assuming the stream is over".format(
                                no_data_timeout, sequence, session
                            )
                        )
                        break
                else:
                    # No timeout, the user needs to cancel this externally
                    resp: HttpMediaResponse = await coro
                logger.debug("Got one response from queue {}".format(id(queue)))
                if resp.session is not None:
                    session = resp.session
                if resp.encrypted and isinstance(resp.plaintext, Exception):
                    raise resp.plaintext
                # print(resp.plaintext)
                tsReader.setBuffer(list(resp.plaintext))
                pkt = tsReader.getPacket()
                if pkt:
                    if pkt.payloadType == PayloadType.PCMA:
                        resp.audioPayload = pkt.payload

                yield resp

        finally:
            # Ensure the queue is deleted even if the coroutine is canceled externally
            if session in self._sessions:
                del self._sessions[session]

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self._started:
            self._started = False
            self._response_handler_task.cancel()
            self._writer.close()
            await self._writer.wait_closed()
