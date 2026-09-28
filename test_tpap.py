"""Offline tests for the TPAP transport: no camera needed.

A fake camera plays the device side of SPAKE2+ (RFC 9383, P-256) and of the
AES-128-CCM /ds channel, including the password_shadow passwd_id 5 answer that
Tapo C200 5.0 firmware 1.4.6 gives.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import os
import struct

from pytapo.const import EncryptionMethod
import pytest
import requests
from Crypto.Cipher import AES

from pytapo.transport.tpap import spake2p as sp
from pytapo.transport.tpap import tpap as tpap_module
from pytapo.transport.tpap.tpap import Tpap, TpapError, discover_tpap


# --------------------------------------------------------------------------- #
#  sha256_crypt: Drepper's published test vectors
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "key,prefix,expected",
    [
        (
            "Hello world!",
            "$5$saltstring",
            "$5$saltstring$5B8vYYiY.CVt1RlTTf8KbXBH3hsxY/GNooZaBBGWEc5",
        ),
        (
            "Hello world!",
            "$5$rounds=10000$saltstringsaltstring",
            "$5$rounds=10000$saltstringsaltst$"
            "3xv.VbSHBb41AL9AvLeujZkZRBAwqFMz2.opqey6IcA",
        ),
        (
            "This is just a test",
            "$5$rounds=5000$toolongsaltstring",
            "$5$rounds=5000$toolongsaltstrin$"
            "Un/5jzAHMgOGZ5.mWJpuVolil07guHPvOW8mGRcvxa5",
        ),
    ],
)
def test_sha256_crypt_vectors(key, prefix, expected):
    assert sp.sha256_crypt(key, prefix) == expected


def test_sha256_crypt_accepts_camera_prefix():
    # The camera sends the prefix with a trailing "$" and a base64-ish salt.
    out = sp.sha256_crypt("x", "$5$x1hYMevsEYq2APg+$")
    assert out.startswith("$5$x1hYMevsEYq2APg+$") and len(out.split("$")[-1]) == 43


def test_extra_crypt_transforms():
    assert sp.apply_extra_crypt("abc", None) == "abc"
    shadow = {
        "type": "password_shadow",
        "params": {"passwd_id": 5, "passwd_prefix": "$5$saltstring$"},
    }
    assert sp.apply_extra_crypt("Hello world!", shadow) == sp.sha256_crypt(
        "Hello world!", "$5$saltstring"
    )
    sha1 = {"type": "password_shadow", "params": {"passwd_id": 2}}
    assert sp.apply_extra_crypt("abc", sha1) == hashlib.sha1(b"abc").hexdigest()
    with pytest.raises(ValueError):
        sp.apply_extra_crypt(
            "abc", {"type": "password_shadow", "params": {"passwd_id": 9}}
        )


# --------------------------------------------------------------------------- #
#  Fake camera
# --------------------------------------------------------------------------- #
class FakeResponse:
    def __init__(self, body, status=200):
        self.content = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.status_code = status

    def json(self):
        return json.loads(self.content)


class FakeCamera:
    """Device side of the login. `expected` is the passcode the camera holds."""

    def __init__(self, cloud_password, passcode_kind="sha256", shadow=True):
        self.passcode = (
            sp.sha256_hex_upper(cloud_password)
            if passcode_kind == "sha256"
            else sp.md5_hex(cloud_password)
        )
        self.shadow = shadow
        self.salt = os.urandom(16)
        self.prefix = "$5$" + base64.b64encode(os.urandom(12)).decode()[:16] + "$"
        self.failed_logins = 0
        self.usernames = []
        self.key = self.nonce = None
        self.seq = None
        self.verify = False

    def credential(self):
        if self.shadow:
            return sp.sha256_crypt(self.passcode, self.prefix)
        return self.passcode

    def close(self):
        pass

    def post(self, url, data=None, headers=None, timeout=None, **kwargs):
        if url.endswith("/ds"):
            return self._ds(data)
        body = json.loads(data)["params"]
        if body["sub_method"] == "pake_register":
            return self._register(body)
        return self._share(body)

    def _register(self, body):
        self.usernames.append(body["username"])
        dk = hashlib.pbkdf2_hmac(
            "sha256", self.credential().encode(), self.salt, 5000, 80
        )
        self.w0 = int.from_bytes(dk[:40], "big") % sp.N
        self.w1 = int.from_bytes(dk[40:], "big") % sp.N
        self.y = int.from_bytes(os.urandom(32), "big") % (sp.N - 1) + 1
        self.Y = sp.pt_add(
            sp.pt_mul(self.y, sp.G_POINT), sp.pt_mul(self.w0, sp.N_POINT)
        )
        self.user_random = body["user_random"]
        self.dev_random = base64.b64encode(os.urandom(32)).decode()
        result = {
            "dev_salt": base64.b64encode(self.salt).decode(),
            "dev_share": base64.b64encode(sp.encode_point(self.Y)).decode(),
            "dev_random": self.dev_random,
            "iterations": 5000,
            "cipher_suites": 1,
            "encryption": "aes_128_ccm",
        }
        if self.shadow:
            result["extra_crypt"] = {
                "type": "password_shadow",
                "params": {
                    "passwd_id": 5,
                    "passwd_prefix": self.prefix,
                    "passwd_rounds": 5000,
                },
            }
        return FakeResponse({"error_code": 0, "result": result})

    def _share(self, body):
        Xb = base64.b64decode(body["user_share"])
        X = sp.decode_point(Xb)
        H = sp.pt_add(X, sp.pt_neg(sp.pt_mul(self.w0, sp.M_POINT)))
        L = sp.pt_mul(self.w1, sp.G_POINT)
        Yb = sp.encode_point(self.Y)
        context = hashlib.sha256(
            sp.CONTEXT_TAG
            + base64.b64decode(self.user_random)
            + base64.b64decode(self.dev_random)
        ).digest()
        transcript = sp._len_prefixed(
            context,
            b"",
            b"",
            sp.encode_point(sp.M_POINT),
            sp.encode_point(sp.N_POINT),
            Xb,
            Yb,
            sp.encode_point(sp.pt_mul(self.y, H)),
            sp.encode_point(sp.pt_mul(self.y, L)),
            self.w0.to_bytes(32, "big"),
        )
        ke = hashlib.sha256(transcript).digest()
        conf = sp.hkdf_sha256(ke, None, b"ConfirmationKeys", 64)
        if not hmac.compare_digest(
            base64.b64decode(body["user_confirm"]),
            hmac.new(conf[:32], Yb, hashlib.sha256).digest(),
        ):
            self.failed_logins += 1
            return FakeResponse({"error_code": -40401})
        shared = sp.hkdf_sha256(ke, None, b"SharedKey", 32)
        self.key = sp.hkdf_sha256(
            shared, b"tp-kdf-salt-aes128-key", b"tp-kdf-info-aes128-key", 32
        )[:16]
        self.nonce = sp.hkdf_sha256(
            shared, b"tp-kdf-salt-aes128-iv", b"tp-kdf-info-aes128-iv", 32
        )[:12]
        self.seq = 7
        return FakeResponse(
            {
                "error_code": 0,
                "result": {
                    "dev_confirm": base64.b64encode(
                        hmac.new(conf[32:], Xb, hashlib.sha256).digest()
                    ).decode(),
                    "stok": "fakestok",
                    "start_seq": self.seq,
                    "expired": 3600,
                },
            }
        )

    def _ds(self, body):
        seq = struct.unpack(">I", body[:4])[0]
        if seq != self.seq:
            return FakeResponse({"error_code": -40401})
        nonce = self.nonce[:8] + struct.pack(">I", seq)
        inner = json.loads(
            AES.new(self.key, AES.MODE_CCM, nonce=nonce, mac_len=16).decrypt_and_verify(
                body[4:-16], body[-16:]
            )
        )
        self.seq += 1
        if inner.get("method") != "multipleRequest":
            return FakeResponse({"error_code": -40209})
        responses = [
            {
                "method": r["method"],
                "result": {"echo": r.get("params")},
                "error_code": 0,
            }
            for r in inner["params"]["requests"]
        ]
        reply = json.dumps(
            {"error_code": 0, "result": {"responses": responses}}
        ).encode()
        c = AES.new(self.key, AES.MODE_CCM, nonce=nonce, mac_len=16)
        return FakeResponse(struct.pack(">I", seq) + c.encrypt(reply) + c.digest())


def make_transport(camera, cloud_password="secret pw"):
    t = Tpap(
        "192.0.2.1", 443, "admin", "camera-account-pw", cloudPassword=cloud_password
    )
    t.session = camera
    t.tpapInfo = {"pake": [2]}  # skip the network discover
    return t


# --------------------------------------------------------------------------- #
#  Transport
# --------------------------------------------------------------------------- #
def test_login_with_sha256_shadow_like_c200():
    camera = FakeCamera("secret pw", passcode_kind="sha256", shadow=True)
    t = make_transport(camera)
    reply = t._sendSync(
        {"method": "getDeviceInfo", "params": {"device_info": {"name": ["basic_info"]}}}
    )
    assert reply["result"]["echo"] == {"device_info": {"name": ["basic_info"]}}
    # the app's order: md5 first (refused here), then sha256; the winner is remembered
    assert camera.failed_logins == 1 and t.passcodeIndex == 1
    assert camera.usernames[0] == hashlib.md5(b"admin").hexdigest()


def test_login_with_md5_and_no_shadow():
    camera = FakeCamera("secret pw", passcode_kind="md5", shadow=False)
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert camera.failed_logins == 0 and t.passcodeIndex == 0


def test_relogin_starts_with_the_passcode_that_worked():
    camera = FakeCamera("secret pw", passcode_kind="sha256")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    t._dropSession()
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert camera.failed_logins == 1  # no second wasted attempt


def test_multiple_request_is_passed_through_unchanged():
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    reply = t._sendSync(
        {
            "method": "multipleRequest",
            "params": {
                "requests": [
                    {"method": "a", "params": {}},
                    {"method": "b", "params": {}},
                ]
            },
        }
    )
    assert [r["method"] for r in reply["result"]["responses"]] == ["a", "b"]


def test_wrong_password_raises_the_shared_wording():
    camera = FakeCamera("right pw")
    t = make_transport(camera, cloud_password="wrong pw")
    with pytest.raises(Exception, match="^Invalid authentication data$"):
        t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert camera.failed_logins == 2  # md5 and sha256, then give up


def test_empty_password_never_reaches_the_camera():
    camera = FakeCamera("right pw")
    t = Tpap("192.0.2.1", 443, "invalid", "", cloudPassword="")
    t.session, t.tpapInfo = camera, {"pake": [2]}
    with pytest.raises(Exception, match="^Invalid authentication data$"):
        t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert camera.usernames == []


def test_lockout_reports_temporary_suspension():
    camera = FakeCamera("right pw")
    camera._share = lambda body: FakeResponse(
        {"error_code": -40404, "data": {"code": -40404, "sec_left": 1799}}
    )
    t = make_transport(camera, cloud_password="wrong pw")
    with pytest.raises(
        Exception, match="^Temporary Suspension: Try again in 1799 seconds$"
    ):
        t._sendSync({"method": "getDeviceInfo", "params": {}})


def test_uses_cloud_password_not_camera_account():
    t = Tpap("192.0.2.1", 443, "admin", "camera-account-pw", cloudPassword="cloud pw")
    assert t.password == "cloud pw"
    assert Tpap("192.0.2.1", 443, "admin", "only-pw").password == "only-pw"


# --------------------------------------------------------------------------- #
#  Detection, async interface and failure paths
# --------------------------------------------------------------------------- #


class DiscoverReply:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.mark.parametrize(
    "payload,offered",
    [
        ({"error_code": 0, "result": {"tpap": {"pake": [2], "tls": 1}}}, True),
        ({"error_code": 0, "result": {"tpap": {"pake": [0]}}}, False),
        ({"error_code": -40210}, False),
        (["not", "a", "dict"], False),
        (ValueError("not json"), False),
    ],
)
def test_discover_tpap(monkeypatch, payload, offered):
    monkeypatch.setattr(
        tpap_module.requests, "post", lambda *a, **k: DiscoverReply(payload)
    )
    assert (discover_tpap("192.0.2.1") is not None) == offered


def test_discover_tpap_unreachable(monkeypatch):
    def refuse(*a, **k):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(tpap_module.requests, "post", refuse)
    assert discover_tpap("192.0.2.1") is None


def test_login_discovers_when_needed(monkeypatch):
    camera = FakeCamera("secret pw")
    t = Tpap("192.0.2.1", 443, "admin", "x", cloudPassword="secret pw")
    t.session = camera
    monkeypatch.setattr(tpap_module, "discover_tpap", lambda *a: {"pake": [2]})
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert t.tpapInfo == {"pake": [2]}


def test_username_follows_user_hash_type():
    t = make_transport(FakeCamera("pw"))
    t.tpapInfo = {"pake": [2], "user_hash_type": 1}
    assert t._username() == hashlib.sha256(b"admin").hexdigest().upper()


def test_async_interface_without_hass():
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    assert asyncio.run(t.authenticate()) is True
    reply = asyncio.run(t.send({"method": "getDeviceInfo", "params": {"a": 1}}))
    assert reply["result"]["echo"] == {"a": 1}
    assert t.getEncryptionMethod() == EncryptionMethod.SHA256
    asyncio.run(t.close())
    assert t.stok is None


def test_async_interface_uses_the_hass_executor():
    class FakeHass:
        calls = 0

        async def async_add_executor_job(self, func, *args):
            FakeHass.calls += 1
            return func(*args)

    t = make_transport(FakeCamera("secret pw"))
    t.hass = FakeHass()
    asyncio.run(t.authenticate())
    assert FakeHass.calls == 1


def test_register_refusal_is_not_retried_as_a_password():
    camera = FakeCamera("secret pw")
    camera._register = lambda body: FakeResponse({"error_code": -40209})
    t = make_transport(camera)
    with pytest.raises(TpapError, match="pake_register failed"):
        t._sendSync({"method": "getDeviceInfo", "params": {}})


def test_device_confirmation_mismatch():
    camera = FakeCamera("secret pw", passcode_kind="md5", shadow=False)
    real_share = camera._share

    def forged(body):
        reply = real_share(body)
        data = json.loads(reply.content)
        data["result"]["dev_confirm"] = base64.b64encode(b"\x00" * 32).decode()
        return FakeResponse(data)

    camera._share = forged
    t = make_transport(camera)
    with pytest.raises(TpapError, match="device confirmation mismatch"):
        t._sendSync({"method": "getDeviceInfo", "params": {}})


def test_refused_request_logs_in_again_once():
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    camera.seq += 5  # camera-side session state moves on: next request is refused
    reply = t._sendSync({"method": "getDeviceInfo", "params": {"again": True}})
    assert reply["result"]["echo"] == {"again": True}


def test_network_error_retries_once_then_raises():
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    real_post = camera.post
    failures = {"left": 1}

    def flaky(url, **kwargs):
        if url.endswith("/ds") and failures["left"]:
            failures["left"] -= 1
            raise requests.ConnectionError("blip")
        return real_post(url, **kwargs)

    camera.post = flaky
    assert t._sendSync({"method": "x", "params": {}})["method"] == "x"

    def down(url, **kwargs):
        raise requests.ConnectionError("down")

    camera.post = down
    with pytest.raises(requests.ConnectionError):
        t._sendSync({"method": "x", "params": {}})


@pytest.mark.parametrize(
    "body,message",
    [
        (b"{not json", "request refused"),
        (b"\x00\x00\x00\x07short", "short reply"),
        (b"\x00\x00\x00\x07" + b"\x00" * 40, "failed authentication"),
    ],
)
def test_bad_replies_raise(body, message):
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    camera._ds = lambda data: FakeResponse(body)
    with pytest.raises(TpapError, match=message):
        t._roundTrip(b"{}")


def test_single_request_with_no_responses_returns_the_whole_reply():
    camera = FakeCamera("secret pw")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    t._roundTrip = lambda payload: {"error_code": 0, "result": {"responses": []}}
    assert t._sendSync({"method": "a", "params": {}}) == {
        "error_code": 0,
        "result": {"responses": []},
    }


def test_point_helpers_edge_cases():
    assert sp.pt_add(None, sp.G_POINT) == sp.G_POINT
    assert sp.pt_add(sp.G_POINT, None) == sp.G_POINT
    assert sp.pt_add(sp.G_POINT, sp.pt_neg(sp.G_POINT)) is None
    assert sp.decode_point(sp.encode_point(sp.G_POINT)) == sp.G_POINT
    with pytest.raises(ValueError):
        sp.decode_point(b"\x05" + b"\x00" * 64)
    with pytest.raises(ValueError):
        sp.apply_extra_crypt("pw", {"type": "password_authkey", "params": {}})


def refuse_next_shares(camera, count):
    """Make the fake camera refuse the next `count` correct pake_share calls,
    like a C200 does for the first login after a session ends."""
    real_share = camera._share
    left = {"n": count}

    def share(body):
        if left["n"]:
            left["n"] -= 1
            camera.failed_logins += 1
            return FakeResponse({"error_code": -40401})
        return real_share(body)

    camera._share = share


def test_relogin_retries_the_known_passcode_after_a_refusal(monkeypatch):
    sleeps = []
    monkeypatch.setattr(tpap_module.time, "sleep", sleeps.append)
    camera = FakeCamera("secret pw", passcode_kind="sha256")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})  # md5 refused, sha256 ok
    t._dropSession()
    refuse_next_shares(camera, 1)
    reply = t._sendSync({"method": "getDeviceInfo", "params": {"after": "renewal"}})
    assert reply["result"]["echo"] == {"after": "renewal"}
    assert sleeps == [tpap_module.RELOGIN_RETRY_DELAY_SECONDS]
    assert t.passcodeIndex == 1


def test_relogin_never_falls_back_to_another_passcode(monkeypatch):
    monkeypatch.setattr(tpap_module.time, "sleep", lambda seconds: None)
    camera = FakeCamera("secret pw", passcode_kind="sha256")
    t = make_transport(camera)
    t._sendSync({"method": "getDeviceInfo", "params": {}})
    t._dropSession()
    tried = []
    real_login_with = t._loginWith

    def spy(passcode):
        tried.append(passcode)
        return real_login_with(passcode)

    t._loginWith = spy
    refuse_next_shares(camera, 2)
    with pytest.raises(Exception, match="^Invalid authentication data$"):
        t._sendSync({"method": "getDeviceInfo", "params": {}})
    assert tried == [sp.sha256_hex_upper("secret pw")] * 2


@pytest.mark.parametrize(
    "payload,rejects",
    [
        ({"error_code": -40211}, True),  # new-firmware camera (e.g. C510W 1.3.4)
        ({"error_code": -40413, "result": {"data": {"encrypt_type": ["3"]}}}, False),
        (["not", "a", "dict"], False),
        (ValueError("not json"), False),
    ],
)
def test_rejects_legacy_login(monkeypatch, payload, rejects):
    monkeypatch.setattr(
        tpap_module.requests, "post", lambda *a, **k: DiscoverReply(payload)
    )
    assert tpap_module.rejects_legacy_login("192.0.2.1") is rejects


def test_rejects_legacy_login_unreachable(monkeypatch):
    def refuse(*a, **k):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(tpap_module.requests, "post", refuse)
    assert tpap_module.rejects_legacy_login("192.0.2.1") is False
