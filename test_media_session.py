"""Offline tests: per-response work of a media stream runs off the event loop and stays correct."""

import asyncio
import threading

from rtp import PayloadType

from pytapo.const import EncryptionMethod
from pytapo.media_stream.crypto import AESHelper
from pytapo.media_stream.session import HttpMediaSession
from test_tsReader import SAMPLES, g711_pes, pat, pmt

TS = pat([(1, 0x1000)]) + pmt(0x1000, [(0x90, 0x101)]) + g711_pes(0x101, SAMPLES)


def _aes():
    return AESHelper(b"admin", b"nonce", b"cloud", b"", EncryptionMethod.MD5)


class FakeWriter:
    def __init__(self):
        self.data = b""

    def write(self, data):
        self.data += data

    async def drain(self):
        pass


def _session():
    s = HttpMediaSession("127.0.0.1", "cloud", "", EncryptionMethod.MD5)
    s._aes = _aes()
    s._writer = FakeWriter()
    return s


def _response(body, session=7, encrypted=True, mimetype="video/mp2t"):
    head = (
        b"--device-stream-boundary--\r\n"
        + b"Content-Type: " + mimetype.encode() + b"\r\n"
        + b"Content-Length: " + str(len(body)).encode() + b"\r\n"
        + b"X-If-Encrypt: " + (b"1" if encrypted else b"0") + b"\r\n"
        + b"X-Session-Id: " + str(session).encode() + b"\r\n\r\n"
    )
    return head + body


def test_decrypt_matches_encrypt_and_is_independent_per_call():
    aes = _aes()
    messages = [bytes([i]) * (100 + i) for i in range(20)]
    ciphertexts = [aes.encrypt(m) for m in messages]
    results = {}

    def work(i):
        results[i] = aes.decrypt(ciphertexts[i])

    threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    # encrypt keeps using the shared cipher on this thread meanwhile
    for m in messages:
        aes.encrypt(m)
    for t in threads:
        t.join()
    assert [results[i] for i in range(20)] == messages


def test_responses_are_decrypted_in_a_worker_thread(monkeypatch):
    s = _session()
    threads = []
    real = s._aes.decrypt

    def decrypt(data):
        threads.append(threading.current_thread())
        return real(data)

    monkeypatch.setattr(s._aes, "decrypt", decrypt)

    async def run():
        s._reader = asyncio.StreamReader()
        s._reader.feed_data(_response(s._aes.encrypt(TS)) + _response(b"not encrypted", encrypted=False))
        s._sessions[7] = asyncio.Queue()
        s._started = True
        task = asyncio.ensure_future(s._device_response_handler_loop())
        first = await asyncio.wait_for(s._sessions[7].get(), 2)
        second = await asyncio.wait_for(s._sessions[7].get(), 2)
        task.cancel()
        return first, second

    first, second = asyncio.run(run())
    assert first.plaintext == TS
    assert second.plaintext == b"not encrypted"
    assert threads and threading.main_thread() not in threads


def test_wrong_cloud_password_is_reported_to_the_receiver():
    s = _session()
    other = AESHelper(b"admin", b"nonce", b"wrong", b"", EncryptionMethod.MD5)

    async def run():
        s._reader = asyncio.StreamReader()
        s._reader.feed_data(_response(other.encrypt(TS)))
        s._sessions[7] = asyncio.Queue()
        s._started = True
        task = asyncio.ensure_future(s._device_response_handler_loop())
        resp = await asyncio.wait_for(s._sessions[7].get(), 2)
        task.cancel()
        return resp

    resp = asyncio.run(run())
    assert isinstance(resp.plaintext, ValueError)
    assert "cloud password" in str(resp.plaintext)


def test_audio_is_searched_in_a_worker_thread(monkeypatch):
    s = _session()
    threads = []
    real = HttpMediaSession._find_audio

    def find_audio(tsReader, plaintext):
        threads.append(threading.current_thread())
        return real(tsReader, plaintext)

    monkeypatch.setattr(HttpMediaSession, "_find_audio", staticmethod(find_audio))

    async def run():
        s._reader = asyncio.StreamReader()
        s._reader.feed_data(_response(s._aes.encrypt(TS)))
        s._sessions[7] = asyncio.Queue()
        s._started = True
        handler = asyncio.ensure_future(s._device_response_handler_loop())
        stream = s.transceive(b"", mimetype="video/mp2t", session=7, no_data_timeout=2)
        resp = await asyncio.wait_for(stream.__anext__(), 2)
        await stream.aclose()
        handler.cancel()
        return resp

    resp = asyncio.run(run())
    assert (resp.audioPayloadType, resp.audioPayload) == (PayloadType.PCMA, SAMPLES)
    assert threads and threading.main_thread() not in threads
